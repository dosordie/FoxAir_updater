#!/usr/bin/env python3
"""Linux/Raspberry-Pi orchestration for the autonomous FoxAir DTU OTA runner.

The host only prepares, starts and observes a persistent DTU-side run. Once
started, loss of this process, USB or ADB does not stop the Mainboard OTA.
Successful and same-version terminal results are archived locally before ACK
and cleanup remove the per-run updater data from the DTU.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

for candidate in (Path(__file__).resolve().parents[2], Path.cwd()):
    if (candidate / "updater/common/adb_transport.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from updater.common.adb_transport import AdbClient, TransportError
from updater.common.firmware_manifest import ManifestError
from updater.dtu_ota import diagnostics, diagnostics_current_run
from updater.dtu_ota.client import DtuOtaClient, RunnerClientError
from updater.dtu_ota.package import PackageError

POLL_SECONDS = 2.0
RECONCILE_AFTER_SECONDS = 10.0
SUCCESS_RESULTS = {"success", "same-version"}
DIAGNOSTIC_ONLY_RESULTS = {
    "failed",
    "recovery-required",
    "reboot-detected",
    "runner-lost",
}


class CliError(RuntimeError):
    pass


class RunLog:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = directory / f"FoxAir_Update_{stamp}.log"
        self.path.write_text("", encoding="utf-8")

    def write(self, text: str, *, error: bool = False) -> None:
        line = text.rstrip()
        stream = sys.stderr if error else sys.stdout
        print(line, file=stream, flush=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def app_version(root: Path) -> str:
    try:
        value = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    except OSError:
        value = ""
    return f"linux-cli-{value or 'unknown'}"


def status_line(status: dict[str, Any]) -> str:
    phase = str(status.get("phase") or "unknown")
    progress = status.get("progress")
    offset = status.get("offset")
    length = status.get("length")
    recovery = str(status.get("recovery") or "")

    parts = [phase]
    if isinstance(progress, int) and progress > 0:
        parts.append(f"{progress} %")
    if isinstance(offset, int) and isinstance(length, int) and length > 0:
        parts.append(f"{offset} / {length} Byte")
    if recovery and recovery != "not-required":
        parts.append(f"Recovery: {recovery}")
    return " | ".join(parts)


def _verify_archive(path: Path, run_id: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise CliError(f"Diagnosearchiv wurde nicht sicher angelegt: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise CliError(f"Diagnosearchiv ist beschädigt: {bad}")
            manifest = json.loads(archive.read("diagnostic_manifest.json").decode("utf-8"))
    except (OSError, KeyError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        raise CliError(f"Diagnosearchiv konnte nicht verifiziert werden: {error}") from error
    if manifest.get("run_id") != run_id:
        raise CliError("Diagnosearchiv gehört nicht zum erwarteten DTU-Lauf")


def create_diagnostic_bundle(
    adb: AdbClient,
    *,
    run_id: str,
    logs_dir: Path,
    host_log: Path,
    version: str,
) -> Path:
    archive = logs_dir / f"FoxAir_DTU_Logs_{run_id}.zip"
    original_runtime_files = diagnostics.LIVE_RUNTIME_TEXT_FILES
    try:
        diagnostics.LIVE_RUNTIME_TEXT_FILES = diagnostics_current_run.runtime_files_for_run(
            adb, run_id
        )
        result = diagnostics.create_bundle(
            adb,
            archive,
            run_id=run_id,
            host_log=host_log,
            host_log_dir=logs_dir,
            app_version=version,
        )
    finally:
        diagnostics.LIVE_RUNTIME_TEXT_FILES = original_runtime_files
    if result.get("ok") is not True:
        raise CliError("Diagnosepaket wurde nicht erfolgreich erstellt")
    _verify_archive(archive, run_id)
    return archive


def finalize_status(
    client: DtuOtaClient,
    adb: AdbClient,
    status: dict[str, Any],
    *,
    logs_dir: Path,
    run_log: RunLog,
    version: str,
) -> int:
    run_id = str(status.get("run_id") or "").strip()
    result_type = str(status.get("result_type") or "").strip()
    if not run_id:
        raise CliError("Terminaler Runner-Status enthält keine Run-ID")

    run_log.write(f"[..] Sichere Diagnose für DTU-Lauf {run_id}")
    try:
        archive = create_diagnostic_bundle(
            adb,
            run_id=run_id,
            logs_dir=logs_dir,
            host_log=run_log.path,
            version=version,
        )
    except (CliError, RuntimeError, TransportError, OSError) as error:
        run_log.write(
            f"[WARNUNG] Diagnose konnte nicht sicher lokal gespeichert werden: {error}",
            error=True,
        )
        run_log.write(
            "[WARNUNG] DTU-Daten bleiben unverändert erhalten; kein ACK/Cleanup ausgeführt.",
            error=True,
        )
        return 2

    run_log.write(f"[OK] Diagnosepaket lokal gespeichert: {archive}")

    if result_type not in SUCCESS_RESULTS:
        run_log.write(
            f"[WARNUNG] Ergebnis {result_type or '<unbekannt>'}: Diagnosedaten bleiben auf dem LTE-Modem erhalten.",
            error=True,
        )
        return 2

    try:
        client.acknowledge(run_id)
        run_log.write("[OK] Terminales DTU-Ergebnis bestätigt")
        client.cleanup(run_id)
    except (RunnerClientError, TransportError, OSError, ValueError) as error:
        run_log.write(
            f"[WARNUNG] Lokales Archiv ist sicher, aber ACK/Cleanup ist fehlgeschlagen: {error}",
            error=True,
        )
        run_log.write(
            "[WARNUNG] Gespeicherte Updatedaten bleiben auf dem LTE-Modem erhalten.",
            error=True,
        )
        return 2

    run_log.write("[OK] Gespeicherte Updatedaten vom LTE-Modem entfernt")
    if result_type == "same-version":
        run_log.write("[OK] Gleiche Firmware erkannt; es wurden keine Firmwaredaten übertragen.")
    else:
        run_log.write("[OK] Firmwareupdate erfolgreich abgeschlossen.")
    return 0


def discard_prepared_run(client: DtuOtaClient, status: dict[str, Any]) -> None:
    run_id = str(status.get("run_id") or "").strip()
    if not run_id:
        raise CliError("Vorprüfungs-Lauf enthält keine Run-ID")
    client.discard_prepared(run_id)


def run_check(
    client: DtuOtaClient,
    manifest: Path,
    *,
    run_log: RunLog,
) -> int:
    status = client.prepare(
        manifest_path=manifest,
        mode="full",
        restart_service_before_update=True,
        isolate_mqtt=False,
    )
    run_log.write(f"[OK] Autonomer DTU-Preflight erfolgreich: {status_line(status)}")
    discard_prepared_run(client, status)
    run_log.write("[OK] Vorprüfungsdaten wieder vom LTE-Modem entfernt; kein OTA wurde gestartet.")
    return 0


def monitor_run(
    client: DtuOtaClient,
    adb: AdbClient,
    run_id: str,
    *,
    logs_dir: Path,
    run_log: RunLog,
    version: str,
) -> int:
    last_signature: tuple[object, ...] | None = None
    last_updated_at: int | None = None
    same_since = time.monotonic()
    last_reconcile = 0.0

    while True:
        now = time.monotonic()
        reconcile = (
            last_updated_at is not None
            and now - same_since >= RECONCILE_AFTER_SECONDS
            and now - last_reconcile >= RECONCILE_AFTER_SECONDS
        )
        try:
            status = client.status(run_id, reconcile=reconcile)
        except (RunnerClientError, TransportError, OSError, ValueError) as error:
            run_log.write(
                f"[WARNUNG] Host-Monitoring unterbrochen: {error}",
                error=True,
            )
            run_log.write(
                f"[WARNUNG] Der gestartete DTU-Lauf {run_id} arbeitet autonom weiter. "
                "Nach wiederhergestellter ADB-Verbindung './foxair-updater status' ausführen.",
                error=True,
            )
            return 3

        updated_at = status.get("updated_at")
        if isinstance(updated_at, int) and updated_at != last_updated_at:
            last_updated_at = updated_at
            same_since = now
            last_reconcile = 0.0
        elif reconcile:
            last_reconcile = now

        signature = (
            status.get("phase"),
            status.get("progress"),
            status.get("offset"),
            status.get("length"),
            status.get("recovery"),
            status.get("result_type"),
            status.get("terminal"),
        )
        if signature != last_signature:
            run_log.write(f"[..] {status_line(status)}")
            last_signature = signature

        result_type = str(status.get("result_type") or "")
        recovery = str(status.get("recovery") or "")
        if status.get("terminal") is True:
            return finalize_status(
                client,
                adb,
                status,
                logs_dir=logs_dir,
                run_log=run_log,
                version=version,
            )
        if recovery == "required" or result_type in DIAGNOSTIC_ONLY_RESULTS:
            return finalize_status(
                client,
                adb,
                status,
                logs_dir=logs_dir,
                run_log=run_log,
                version=version,
            )
        time.sleep(POLL_SECONDS)


def run_update(
    client: DtuOtaClient,
    adb: AdbClient,
    manifest: Path,
    *,
    logs_dir: Path,
    run_log: RunLog,
    version: str,
) -> int:
    prepared = client.prepare(
        manifest_path=manifest,
        mode="full",
        restart_service_before_update=True,
        isolate_mqtt=False,
    )
    run_id = str(prepared.get("run_id") or "").strip()
    if not run_id:
        raise CliError("DTU-Preflight lieferte keine Run-ID")
    run_log.write(f"[OK] DTU-Preflight erfolgreich: {run_id}")
    started = client.start(run_id)
    run_log.write(f"[OK] Autonomer DTU-Runner gestartet: {status_line(started)}")
    run_log.write("[..] Der Mainboard-OTA läuft ab jetzt unabhängig von dieser Host-/ADB-Verbindung.")
    return monitor_run(
        client,
        adb,
        run_id,
        logs_dir=logs_dir,
        run_log=run_log,
        version=version,
    )


def run_status(
    client: DtuOtaClient,
    adb: AdbClient,
    *,
    logs_dir: Path,
    run_log: RunLog,
    version: str,
) -> int:
    try:
        run_id = client.current_run_id()
    except RunnerClientError as error:
        if str(error) == "DTU has no last_run_id":
            run_log.write("[OK] Kein gespeicherter autonomer OTA-Lauf auf dem LTE-Modem.")
            return 0
        raise
    status = client.status(run_id)
    run_log.write(f"[..] Lauf {run_id}: {status_line(status)}")
    result_type = str(status.get("result_type") or "")
    recovery = str(status.get("recovery") or "")
    if status.get("terminal") is True or recovery == "required" or result_type in DIAGNOSTIC_ONLY_RESULTS:
        return finalize_status(
            client,
            adb,
            status,
            logs_dir=logs_dir,
            run_log=run_log,
            version=version,
        )
    return 0


def confirm_update(manifest: Path) -> bool:
    if not sys.stdin.isatty():
        raise CliError("Nicht-interaktiver Start benötigt weiterhin --confirm")
    answer = input(f"Firmwareupdate mit {manifest.name} autonom starten? [j/N] ").strip().lower()
    return answer in {"j", "ja", "y", "yes"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FoxAir Linux client for autonomous DTU OTA")
    parser.add_argument("--adb", default=os.environ.get("FOX_AIR_ADB", "adb"))
    parser.add_argument("--serial")
    parser.add_argument("--logs-dir", type=Path, required=True)
    parser.add_argument("--root-dir", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check")
    check.add_argument("--manifest", type=Path, required=True)

    update = commands.add_parser("update")
    update.add_argument("--manifest", type=Path, required=True)
    update.add_argument("--yes", action="store_true")

    commands.add_parser("status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logs_dir = args.logs_dir.expanduser().resolve()
    run_log = RunLog(logs_dir)
    adb = AdbClient(args.adb, args.serial, env=os.environ.copy())
    client = DtuOtaClient(adb, source_root=args.root_dir.expanduser().resolve())
    version = app_version(args.root_dir.expanduser().resolve())

    try:
        if args.command == "check":
            return run_check(client, args.manifest.expanduser().resolve(), run_log=run_log)
        if args.command == "update":
            manifest = args.manifest.expanduser().resolve()
            if not args.yes and not confirm_update(manifest):
                run_log.write("[..] Firmwareupdate nicht gestartet.")
                return 0
            return run_update(
                client,
                adb,
                manifest,
                logs_dir=logs_dir,
                run_log=run_log,
                version=version,
            )
        if args.command == "status":
            return run_status(
                client,
                adb,
                logs_dir=logs_dir,
                run_log=run_log,
                version=version,
            )
        raise CliError("Unbekannter Befehl")
    except (CliError, RunnerClientError, PackageError, ManifestError, TransportError, OSError, ValueError) as error:
        run_log.write(f"[FEHLER] {error}", error=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
