#!/usr/bin/env python3
"""Cross-platform maintenance command for the persistent PHNIX statistics block.

This module is deliberately separate from the OTA controller. The exact same
file is usable directly on Linux and is copied byte-for-byte into the Windows
package by the existing ``updater/common/*.py`` build step. The Windows GUI is
only a frontend for this command.

The currently supported write is deliberately narrow: change the persistent
Mainboard OTA operation counter at file offset 0x24 in the exact 128-byte
``/data/phnixIot_device_statisic`` file. No OTA-controller code is imported or
modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

for candidate in (Path(__file__).resolve().parents[2], Path.cwd()):
    if (candidate / "updater/common/adb_transport.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from updater.common.adb_transport import AdbClient
from updater.common.phnix_modem_info import STATISTICS_ADDRESS, read_process_memory

EXPECTED_SERVICE_SHA256 = "7C573431F0A67620D473419644A83A4F4DC04B8A91BDE5923C74A63BA1EAEDB7"
REMOTE_SERVICE = "/data/phnixIot4G"
REMOTE_STATISTICS = "/data/phnixIot_device_statisic"
REMOTE_BACKUP = "/data/.phnixIot_device_statisic.counter-backup"
REMOTE_STAGE = "/data/.phnixIot_device_statisic.counter-stage"
REMOTE_PAYLOAD = "/data/.phnixIot_device_statisic.counter-payload"
REMOTE_RUN_ACTIVE = "/tmp/phnix_ota_hook/run.active"
REMOTE_TRANSFER_STARTED = "/tmp/phnix_ota_hook/transfer-started"
REMOTE_INJECTION_STARTED = "/tmp/phnix_ota_hook/injection-started"
REMOTE_RESCUE_DIR = "/tmp/phnix_statistics_maintenance"
REMOTE_RESCUE_PID = f"{REMOTE_RESCUE_DIR}/rescue.pid"
REMOTE_RESCUE_CANCEL = f"{REMOTE_RESCUE_DIR}/rescue.cancel"
RESCUE_TIMEOUT_SECONDS = 90
SERVICE_SNAPSHOT_ATTEMPTS = 3
SERVICE_SNAPSHOT_DELAY_SECONDS = 0.25
SERVICE_TERM_GRACE_SECONDS = 2.0
SERVICE_KILL_TIMEOUT_SECONDS = 4.0
STATISTICS_SIZE = 128
MAINBOARD_OTA_OFFSET = 0x24
MAINBOARD_OTA_RAM_ADDRESS = STATISTICS_ADDRESS + MAINBOARD_OTA_OFFSET
CONFIRM_TOKEN = "PHNIX-STATISTICS-WRITE"

OUTPUT_MODE = "human"


class MaintenanceError(RuntimeError):
    pass


def emit(event: str, **fields) -> None:
    record = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, **fields}
    if OUTPUT_MODE == "json":
        print(json.dumps(record, ensure_ascii=False), flush=True)
        return
    messages = {
        "inspect": f"Mainboard OTA-Vorgänge: {fields.get('current_value')}",
        "preflight": "Vorprüfung bestanden" if fields.get("ok") else "Vorprüfung fehlgeschlagen",
        "dry-run": f"Trockenlauf: {fields.get('current_value')} -> {fields.get('target_value')}",
        "rescue-armed": f"Watchdog-Rescue für {fields.get('timeout_seconds')} Sekunden aktiviert",
        "watchdogs-paused": "Originale Watchdogs vorübergehend angehalten",
        "service-term": "phnixIot4G wird zunächst mit SIGTERM beendet",
        "service-kill": "phnixIot4G reagiert nicht auf SIGTERM; kontrollierter SIGKILL-Fallback",
        "service-stopped": "phnixIot4G vollständig beendet",
        "state-backed-up": "Finalen 128-Byte-Statistikzustand gesichert",
        "statistics-written": "Statistikdatei atomar ersetzt und geprüft",
        "service-restored": "Originaldienst und Watchdogs wiederhergestellt",
        "complete": f"Mainboard OTA-Vorgänge erfolgreich auf {fields.get('value')} gesetzt",
        "error": f"FEHLER: {fields.get('message')}",
    }
    print(messages.get(event, f"{event}: {fields}"), flush=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def counter_from_bytes(raw: bytes) -> int:
    if len(raw) != STATISTICS_SIZE:
        raise MaintenanceError(f"statistics file has {len(raw)} bytes; expected {STATISTICS_SIZE}")
    return int.from_bytes(raw[MAINBOARD_OTA_OFFSET:MAINBOARD_OTA_OFFSET + 4], "little")


def patch_counter(raw: bytes, value: int) -> bytes:
    if len(raw) != STATISTICS_SIZE:
        raise MaintenanceError(f"statistics file has {len(raw)} bytes; expected {STATISTICS_SIZE}")
    if not 0 <= value <= 0xFFFFFFFF:
        raise MaintenanceError("counter value must be uint32 (0..4294967295)")
    patched = bytearray(raw)
    patched[MAINBOARD_OTA_OFFSET:MAINBOARD_OTA_OFFSET + 4] = value.to_bytes(4, "little")
    return bytes(patched)


def numeric_pids(text: str) -> list[int]:
    return [int(token) for token in text.replace("\r", " ").replace("\n", " ").split() if token.isdigit()]


def service_pids(adb: AdbClient) -> list[int]:
    return numeric_pids(adb.shell("pidof phnixIot4G || true", check=False))


def first_pid(adb: AdbClient) -> int | None:
    pids = service_pids(adb)
    return pids[0] if pids else None


def stable_single_service_snapshot(
    adb: AdbClient,
    *,
    attempts: int = SERVICE_SNAPSHOT_ATTEMPTS,
    delay: float = SERVICE_SNAPSHOT_DELAY_SECONDS,
) -> dict:
    last_pids: list[int] = []
    for attempt in range(attempts):
        pids_before = service_pids(adb)
        last_pids = pids_before
        if len(pids_before) == 1:
            pid = pids_before[0]
            path = adb.shell(f"readlink /proc/{pid}/exe || true", check=False)
            tracer = adb.shell(
                f"awk '/^TracerPid:/ {{print $2}}' /proc/{pid}/status || true",
                check=False,
            )
            pids_after = service_pids(adb)
            last_pids = pids_after
            if pids_before == pids_after == [pid] and path:
                return {
                    "stable": True,
                    "pid": pid,
                    "pids": pids_after,
                    "path": path,
                    "tracer": tracer,
                    "attempts": attempt + 1,
                }
        if attempt < attempts - 1:
            time.sleep(delay)
    return {
        "stable": False,
        "pid": None,
        "pids": last_pids,
        "path": "",
        "tracer": "",
        "attempts": attempts,
    }


def watchdog_pids(adb: AdbClient) -> list[int]:
    return numeric_pids(adb.shell("ps | awk '$4 == \"{helloworld}\" {print $1}'", check=False))


def remote_exists(adb: AdbClient, path: str) -> bool:
    lines = adb.shell(f"test -e '{path}'; echo $?", check=False).splitlines()
    return bool(lines) and lines[-1].strip() == "0"


def pull_exact(adb: AdbClient, remote: str, local: Path, expected_size: int) -> bytes:
    adb.run("pull", remote, str(local))
    raw = local.read_bytes()
    if len(raw) != expected_size:
        raise MaintenanceError(f"{remote} has {len(raw)} bytes; expected {expected_size}")
    return raw


def preflight(adb: AdbClient, scratch: Path) -> dict:
    adb_state = adb.run("get-state").strip()
    snapshot = stable_single_service_snapshot(adb)
    pids = list(snapshot["pids"])
    pid = snapshot["pid"]
    service_path = str(snapshot["path"])
    tracer = str(snapshot["tracer"])
    service_sha = adb.shell(f"sha256sum {REMOTE_SERVICE} | awk '{{print $1}}'", check=False).upper()
    wds = watchdog_pids(adb)
    debugger_pids = adb.shell("pidof gdbserver gdb || true", check=False)
    active_markers = [
        path for path in (REMOTE_RUN_ACTIVE, REMOTE_TRANSFER_STARTED, REMOTE_INJECTION_STARTED)
        if remote_exists(adb, path)
    ]
    raw = pull_exact(adb, REMOTE_STATISTICS, scratch / "preflight-statistics.bin", STATISTICS_SIZE)
    current = counter_from_bytes(raw)
    checks = {
        "adb_device": adb_state == "device",
        "service_stable": bool(snapshot["stable"]),
        "service_singleton": bool(snapshot["stable"]) and len(pids) == 1,
        "service_running": pid is not None,
        "service_path": service_path == REMOTE_SERVICE,
        "service_original": service_sha == EXPECTED_SERVICE_SHA256,
        "service_untraced": tracer.strip() == "0",
        "no_debugger": not debugger_pids.strip(),
        "watchdogs_running": len(wds) >= 2,
        "no_active_ota": not active_markers,
        "statistics_size": len(raw) == STATISTICS_SIZE,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "adb_state": adb_state,
        "service_pid": pid,
        "service_pids": pids,
        "service_snapshot_attempts": snapshot["attempts"],
        "service_path": service_path,
        "service_sha256": service_sha,
        "watchdog_pids": wds,
        "active_markers": active_markers,
        "current_value": current,
        "statistics_sha256": sha256_bytes(raw),
    }


def arm_watchdog_rescue(adb: AdbClient, pids: list[int]) -> None:
    if not pids:
        raise MaintenanceError("cannot arm rescue without watchdog PIDs")
    pid_words = " ".join(str(pid) for pid in pids)
    command = (
        f"mkdir -p {REMOTE_RESCUE_DIR}; "
        f"rm -f {REMOTE_RESCUE_CANCEL} {REMOTE_RESCUE_PID}; "
        f"( sleep {RESCUE_TIMEOUT_SECONDS}; "
        f"if test ! -f {REMOTE_RESCUE_CANCEL}; then "
        f"for p in {pid_words}; do kill -CONT \"$p\" 2>/dev/null || true; done; "
        "fi; "
        f"rm -f {REMOTE_RESCUE_PID} ) </dev/null >/dev/null 2>&1 & "
        f"echo $! > {REMOTE_RESCUE_PID}"
    )
    adb.shell(command)
    if not remote_exists(adb, REMOTE_RESCUE_PID):
        raise MaintenanceError("failed to arm remote watchdog rescue")


def disarm_watchdog_rescue(adb: AdbClient) -> None:
    adb.shell(
        f"touch {REMOTE_RESCUE_CANCEL}; "
        f"if test -f {REMOTE_RESCUE_PID}; then kill \"$(cat {REMOTE_RESCUE_PID})\" 2>/dev/null || true; fi; "
        f"rm -rf {REMOTE_RESCUE_DIR}",
        check=False,
    )


def pause_watchdogs(adb: AdbClient, pids: list[int]) -> None:
    """Freeze supervisors; do not kill them, matching the OTA runtime hook."""
    if not pids:
        raise MaintenanceError("no watchdog PIDs available")
    for pid in pids:
        adb.shell(f"kill -STOP {pid}")


def resume_watchdogs(adb: AdbClient, pids: list[int]) -> None:
    for pid in pids:
        adb.shell(f"kill -CONT {pid} 2>/dev/null || true", check=False)


def wait_service_absent(adb: AdbClient, *, timeout: float, old_pid: int | None = None) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pids = service_pids(adb)
        if not pids:
            return True
        if old_pid is not None and old_pid not in pids:
            raise MaintenanceError("another phnixIot4G instance appeared while watchdogs were paused")
        time.sleep(0.1)
    return False


def stop_service_for_maintenance(adb: AdbClient, old_pid: int) -> str:
    """TERM first, then the same deliberate KILL pattern used by OTA restore."""
    emit("service-term", old_pid=old_pid)
    adb.shell(f"kill -TERM {old_pid}")
    if wait_service_absent(adb, timeout=SERVICE_TERM_GRACE_SECONDS, old_pid=old_pid):
        return "term"

    current = service_pids(adb)
    if current != [old_pid]:
        raise MaintenanceError(
            f"service PID changed during stop sequence: expected [{old_pid}], got {current}"
        )

    emit("service-kill", old_pid=old_pid)
    adb.shell(f"kill -KILL {old_pid}")
    if not wait_service_absent(adb, timeout=SERVICE_KILL_TIMEOUT_SECONDS, old_pid=old_pid):
        raise MaintenanceError("phnixIot4G remained alive after controlled SIGKILL; no file was modified")
    return "kill"


def wait_service_restored(adb: AdbClient, old_pid: int, timeout: float = 25.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pids = service_pids(adb)
        if len(pids) == 1 and pids[0] != old_pid:
            pid = pids[0]
            path = adb.shell(f"readlink /proc/{pid}/exe || true", check=False)
            sha = adb.shell(f"sha256sum {REMOTE_SERVICE} | awk '{{print $1}}'", check=False).upper()
            tracer = adb.shell(
                f"awk '/^TracerPid:/ {{print $2}}' /proc/{pid}/status || true",
                check=False,
            )
            if path == REMOTE_SERVICE and sha == EXPECTED_SERVICE_SHA256 and tracer.strip() == "0":
                return pid
        time.sleep(0.5)
    raise MaintenanceError("original phnixIot4G service did not restart cleanly")


def install_patched_file(adb: AdbClient, patched_local: Path, expected_sha: str) -> None:
    adb.shell(
        f"rm -f {REMOTE_BACKUP} {REMOTE_STAGE} {REMOTE_PAYLOAD}; "
        f"cp -p {REMOTE_STATISTICS} {REMOTE_BACKUP} && "
        f"cp -p {REMOTE_STATISTICS} {REMOTE_STAGE} && sync"
    )
    adb.push(patched_local, REMOTE_PAYLOAD)
    size = adb.shell(f"wc -c < {REMOTE_PAYLOAD}")
    payload_sha = adb.shell(f"sha256sum {REMOTE_PAYLOAD} | awk '{{print $1}}'").upper()
    if size.strip() != str(STATISTICS_SIZE) or payload_sha != expected_sha:
        raise MaintenanceError("staged payload verification failed")
    adb.shell(f"cat {REMOTE_PAYLOAD} > {REMOTE_STAGE} && sync")
    stage_sha = adb.shell(f"sha256sum {REMOTE_STAGE} | awk '{{print $1}}'").upper()
    if stage_sha != expected_sha:
        raise MaintenanceError("metadata-preserving stage verification failed")
    adb.shell(f"mv {REMOTE_STAGE} {REMOTE_STATISTICS} && rm -f {REMOTE_PAYLOAD} && sync")
    final_sha = adb.shell(f"sha256sum {REMOTE_STATISTICS} | awk '{{print $1}}'").upper()
    if final_sha != expected_sha:
        raise MaintenanceError("post-replace statistics SHA256 mismatch")


def restore_remote_backup(adb: AdbClient) -> None:
    if remote_exists(adb, REMOTE_BACKUP):
        adb.shell(
            f"cp -p {REMOTE_BACKUP} {REMOTE_STAGE} && "
            f"mv {REMOTE_STAGE} {REMOTE_STATISTICS} && "
            f"rm -f {REMOTE_PAYLOAD} {REMOTE_BACKUP} && sync",
            check=False,
        )


def cleanup_remote(adb: AdbClient) -> None:
    adb.shell(f"rm -f {REMOTE_BACKUP} {REMOTE_STAGE} {REMOTE_PAYLOAD}", check=False)


def inspect_command(adb: AdbClient) -> int:
    with tempfile.TemporaryDirectory(prefix="phnix-stat-inspect-") as temp:
        result = preflight(adb, Path(temp))
    emit("inspect", **result)
    return 0 if result["ok"] else 2


def set_command(
    adb: AdbClient,
    value: int,
    *,
    execute: bool,
    confirm: str | None,
    backup_dir: Path,
) -> int:
    with tempfile.TemporaryDirectory(prefix="phnix-stat-maint-") as temp_name:
        temp = Path(temp_name)
        before = preflight(adb, temp)
        emit("preflight", **before)
        if not before["ok"]:
            failed = ", ".join(name for name, ok in before["checks"].items() if not ok)
            raise MaintenanceError("preflight failed: " + failed)
        if not execute:
            emit("dry-run", current_value=before["current_value"], target_value=value)
            return 0
        if confirm != CONFIRM_TOKEN:
            raise MaintenanceError(f"write requires --confirm {CONFIRM_TOKEN}")

        old_pid = int(before["service_pid"])
        wds = list(before["watchdog_pids"])
        rescue_armed = False
        paused = False
        replaced = False
        try:
            arm_watchdog_rescue(adb, wds)
            rescue_armed = True
            emit("rescue-armed", timeout_seconds=RESCUE_TIMEOUT_SECONDS, watchdog_pids=wds)

            pause_watchdogs(adb, wds)
            paused = True
            emit("watchdogs-paused", watchdog_pids=wds)

            stop_method = stop_service_for_maintenance(adb, old_pid)
            emit("service-stopped", old_pid=old_pid, method=stop_method, watchdog_pids=wds)
            time.sleep(0.15)

            # Re-read only after no service exists so an orderly TERM flush, if
            # it occurred, is included in the authoritative file we patch.
            final_path = temp / "final-statistics.bin"
            final_raw = pull_exact(adb, REMOTE_STATISTICS, final_path, STATISTICS_SIZE)
            current_after_stop = counter_from_bytes(final_raw)
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            backup_path = backup_dir / (
                "phnixIot_device_statisic."
                f"{stamp}.before-counter-{current_after_stop}.bin"
            )
            shutil.copy2(final_path, backup_path)
            emit(
                "state-backed-up",
                path=str(backup_path),
                sha256=sha256_bytes(final_raw),
                current_value=current_after_stop,
            )

            patched = patch_counter(final_raw, value)
            if (
                final_raw[:MAINBOARD_OTA_OFFSET] != patched[:MAINBOARD_OTA_OFFSET]
                or final_raw[MAINBOARD_OTA_OFFSET + 4:] != patched[MAINBOARD_OTA_OFFSET + 4:]
            ):
                raise MaintenanceError("internal patch guard failed: bytes outside offset 0x24 changed")
            patched_path = temp / "patched-statistics.bin"
            patched_path.write_bytes(patched)
            patched_sha = sha256_bytes(patched)
            install_patched_file(adb, patched_path, patched_sha)
            replaced = True
            emit("statistics-written", old_value=current_after_stop, new_value=value, sha256=patched_sha)

            # Same restoration model as the original OTA runtime hook: the
            # watchdogs remain alive, are resumed, and start a fresh service.
            resume_watchdogs(adb, wds)
            paused = False
            new_pid = wait_service_restored(adb, old_pid)

            verify_file = pull_exact(adb, REMOTE_STATISTICS, temp / "verify-statistics.bin", STATISTICS_SIZE)
            file_value = counter_from_bytes(verify_file)
            try:
                ram_raw = read_process_memory(adb, new_pid, MAINBOARD_OTA_RAM_ADDRESS, 4, attempts=3)
                ram_value = int.from_bytes(ram_raw, "little")
            except Exception as exc:
                raise MaintenanceError(f"RAM verification failed after restart: {exc}") from exc
            if file_value != value or ram_value != value:
                raise MaintenanceError(
                    f"verification mismatch: file={file_value}, RAM={ram_value}, expected={value}"
                )

            cleanup_remote(adb)
            emit("service-restored", service_pid=new_pid, watchdog_pids=watchdog_pids(adb))
            emit(
                "complete",
                value=value,
                file_value=file_value,
                ram_value=ram_value,
                stop_method=stop_method,
                backup=str(backup_path),
            )
            return 0
        except BaseException:
            if replaced and first_pid(adb) is None:
                restore_remote_backup(adb)
            raise
        finally:
            if paused:
                resume_watchdogs(adb, wds)
            if rescue_armed:
                disarm_watchdog_rescue(adb)
            cleanup_remote(adb)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Read or experimentally change PHNIX persistent statistics via ADB")
    p.add_argument("--adb", default="adb", help="adb/adb.exe path")
    p.add_argument("--serial", default=None)
    p.add_argument("--output", choices=("human", "json"), default="human")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="read-only preflight and current Mainboard OTA operation counter")
    set_p = sub.add_parser("set-mainboard-ota-count", help="set uint32 counter at statistics offset 0x24")
    set_p.add_argument("value", type=int)
    set_p.add_argument("--execute", action="store_true", help="actually perform the maintenance write")
    set_p.add_argument("--confirm", default=None)
    set_p.add_argument(
        "--backup-dir",
        type=Path,
        default=Path.home() / "FoxAir_LTE_Backup" / "statistics-maintenance",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    global OUTPUT_MODE
    args = parser().parse_args(argv)
    OUTPUT_MODE = args.output
    adb = AdbClient(args.adb, serial=args.serial)
    try:
        if args.command == "show":
            return inspect_command(adb)
        return set_command(
            adb,
            args.value,
            execute=args.execute,
            confirm=args.confirm,
            backup_dir=args.backup_dir,
        )
    except Exception as exc:
        emit("error", message=str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
