#!/usr/bin/env python3
"""Fail-closed original-state check/restore without the legacy host OTA controller.

This module is intentionally narrow. It never starts a Mainboard OTA. It can
read the normal PHNIX runtime state and, when no autonomous runner or accepted
firmware transfer owns the modem, invoke the already-proven runtime hook
restore-original action to release a pre-transfer guarded state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

for candidate in (Path(__file__).resolve().parents[2], Path.cwd()):
    if (candidate / "updater/common/adb_transport.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from updater.common.adb_transport import AdbClient, TransportError
from updater.dtu_ota.package import EXPECTED_SERVICE_SHA256

REMOTE_SERVICE = "/data/phnixIot4G"
REMOTE_HELPER = "/data/phnix_ota_runtime_hook"
REMOTE_HELPER_STAGE = "/data/.phnix_ota_runtime_hook.new"
REMOTE_STAGE_DIR = "/data/phnix_local_ota"
REMOTE_STATUS = "/tmp/phnix_ota_status.json"
REMOTE_HTTP_PID = "/tmp/phnix_ota_httpd.pid"
REMOTE_HOOK_STATE = "/tmp/phnix_ota_hook"
REMOTE_TRANSFER_STARTED = f"{REMOTE_HOOK_STATE}/transfer-started"
REMOTE_INJECTION_STARTED = f"{REMOTE_HOOK_STATE}/injection-started"
REMOTE_ORIGINAL_SERVICE_OWNS = f"{REMOTE_HOOK_STATE}/original-service-owns"
REMOTE_RUN_ACTIVE = f"{REMOTE_HOOK_STATE}/run.active"
REMOTE_HANDSHAKE_TRACE = "/tmp/phnix_handshake_trace.json"
REMOTE_RUNNER_LOCK = "/data/foxair_ota_runner/active.lock/run_id"
RESTORE_CONFIRM_TOKEN = "FOXAIR-RESTORE-ORIGINAL"
DEFAULT_RESTORE_TIMEOUT = 120.0
POLL_SECONDS = 2.0


class OriginalStateError(RuntimeError):
    pass


def _exists(adb: AdbClient, path: str) -> bool:
    return adb.shell(f"test -e '{path}' && echo 1 || true") == "1"


def _read(adb: AdbClient, path: str) -> str:
    return adb.shell(f"cat '{path}' 2>/dev/null || true").strip()


def _service_pids(adb: AdbClient) -> list[str]:
    raw = adb.shell("pidof phnixIot4G 2>/dev/null || true")
    return [item for item in raw.split() if item.isdigit()]


def _watchdog_pids(adb: AdbClient) -> list[str]:
    raw = adb.shell("ps | awk '$4 == \"{helloworld}\" {print $1}'")
    return [item for item in raw.split() if item.isdigit()]


def _mqtt_established(adb: AdbClient) -> tuple[bool, str]:
    lines = adb.shell(
        "netstat -nt 2>/dev/null | awk '$4 ~ /:1883$/ || $5 ~ /:1883$/ {print}'"
    )
    return any("ESTABLISHED" in line for line in lines.splitlines()), lines


def original_state_snapshot(adb: AdbClient) -> dict[str, Any]:
    pids = _service_pids(adb)
    service_pid = pids[0] if len(pids) == 1 else ""
    service_path = (
        adb.shell(f"readlink /proc/{service_pid}/exe 2>/dev/null || true")
        if service_pid
        else ""
    )
    service_sha256 = adb.shell(
        f"sha256sum '{REMOTE_SERVICE}' 2>/dev/null | awk '{{print $1}}'"
    ).upper()
    tracer = (
        adb.shell(
            f"awk '/^TracerPid:/ {{print $2}}' /proc/{service_pid}/status 2>/dev/null || true"
        )
        if service_pid
        else ""
    )
    watchdogs = _watchdog_pids(adb)
    cloud_connected, mqtt_lines = _mqtt_established(adb)
    active_runner = _read(adb, REMOTE_RUNNER_LOCK)
    markers = {
        "run_active": _exists(adb, REMOTE_RUN_ACTIVE),
        "injection_started": _exists(adb, REMOTE_INJECTION_STARTED),
        "transfer_started": _exists(adb, REMOTE_TRANSFER_STARTED),
        "original_service_owns": _exists(adb, REMOTE_ORIGINAL_SERVICE_OWNS),
    }
    helper_present = _exists(adb, REMOTE_HELPER)

    checks = {
        "single_service": len(pids) == 1,
        "service_path": service_path == REMOTE_SERVICE,
        "service_original": service_sha256 == EXPECTED_SERVICE_SHA256,
        "service_untraced": tracer.strip() == "0",
        "watchdogs_running": len(watchdogs) >= 2,
        "cloud_connected": cloud_connected,
        "runtime_helper_absent": not helper_present,
        "no_active_runner": not bool(active_runner),
        "legacy_runtime_clear": not any(markers.values()),
    }
    original_ok = all(checks.values())
    return {
        "ok": original_ok,
        "original_ok": original_ok,
        "checks": checks,
        "service_pid": service_pid or None,
        "service_pids": pids,
        "service_path": service_path or None,
        "service_sha256": service_sha256 or None,
        "watchdog_pids": watchdogs,
        "mqtt_connection": mqtt_lines,
        "active_runner": active_runner or None,
        "legacy_markers": markers,
        "runtime_helper_present": helper_present,
    }


def _local_hook_path() -> Path:
    path = Path(__file__).resolve().parent / "payload" / "phnix_ota_runtime_hook"
    if not path.is_file():
        raise OriginalStateError(f"Runtime-Hook fehlt: {path}")
    raw = path.read_bytes()
    if not raw.startswith(b"#!/bin/sh\n") or b"\r" in raw:
        raise OriginalStateError(
            "Runtime-Hook ist nicht im erwarteten LF-/#!/bin/sh-Format"
        )
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def _remote_sha256(adb: AdbClient, path: str) -> str:
    return adb.shell(
        f"sha256sum '{path}' 2>/dev/null | awk '{{print $1}}'"
    ).lower()


def _install_verified_hook(adb: AdbClient, local_hook: Path) -> None:
    expected = _sha256_file(local_hook)
    if _exists(adb, REMOTE_HELPER):
        remote = _remote_sha256(adb, REMOTE_HELPER)
        if remote == expected:
            adb.shell(f"chmod 700 '{REMOTE_HELPER}'")
            return
        active_legacy = any(
            _exists(adb, marker)
            for marker in (REMOTE_RUN_ACTIVE, REMOTE_INJECTION_STARTED)
        )
        if active_legacy:
            raise OriginalStateError(
                "Aktiver Legacy-Recovery-Zustand verwendet einen unbekannten Runtime-Hook; "
                "automatischer Austausch wird verweigert."
            )

    adb.push(local_hook, REMOTE_HELPER_STAGE)
    remote_stage = _remote_sha256(adb, REMOTE_HELPER_STAGE)
    if remote_stage != expected:
        adb.shell(f"rm -f '{REMOTE_HELPER_STAGE}'", check=False)
        raise OriginalStateError("SHA-256 des übertragenen Runtime-Hooks stimmt nicht")
    adb.shell(
        f"chmod 700 '{REMOTE_HELPER_STAGE}' && "
        f"mv '{REMOTE_HELPER_STAGE}' '{REMOTE_HELPER}' && sync"
    )
    if _remote_sha256(adb, REMOTE_HELPER) != expected:
        raise OriginalStateError("Installierter Runtime-Hook konnte nicht verifiziert werden")


def _stop_legacy_http(adb: AdbClient) -> None:
    adb.shell(
        f"test -f '{REMOTE_HTTP_PID}' && kill $(cat '{REMOTE_HTTP_PID}') 2>/dev/null || true; "
        "for p in $(ps | awk '$4 == \"busybox\" && $5 == \"httpd\" {print $1}'); do "
        "cmd=$(tr '\\000' ' ' < /proc/$p/cmdline 2>/dev/null || true); "
        "case \"$cmd\" in *\"httpd -p 127.0.0.1:8081\"*\"-h /data/phnix_local_ota\"*) "
        "kill $p 2>/dev/null || true ;; esac; done; "
        f"rm -f '{REMOTE_HTTP_PID}'",
        check=False,
    )


def _remove_legacy_artifacts(adb: AdbClient) -> None:
    _stop_legacy_http(adb)
    adb.shell(
        f"rm -rf '{REMOTE_STAGE_DIR}' '{REMOTE_HOOK_STATE}'; "
        f"rm -f '{REMOTE_STATUS}' '{REMOTE_HANDSHAKE_TRACE}' "
        f"'{REMOTE_HTTP_PID}' '{REMOTE_HELPER}' '{REMOTE_HELPER_STAGE}'; sync"
    )


def _restore_preconditions(adb: AdbClient) -> dict[str, Any]:
    active_runner = _read(adb, REMOTE_RUNNER_LOCK)
    markers = {
        "run_active": _exists(adb, REMOTE_RUN_ACTIVE),
        "injection_started": _exists(adb, REMOTE_INJECTION_STARTED),
        "transfer_started": _exists(adb, REMOTE_TRANSFER_STARTED),
        "original_service_owns": _exists(adb, REMOTE_ORIGINAL_SERVICE_OWNS),
    }
    blockers: list[str] = []
    if active_runner:
        blockers.append(
            f"Autonomer DTU-Lauf {active_runner} ist noch als aktiv markiert; "
            "dessen Runner-/Abort-Pfad bleibt zuständig."
        )
    if markers["transfer_started"] or markers["original_service_owns"]:
        blockers.append(
            "Die Firmwareübertragung wurde bereits vom Originaldienst übernommen; "
            "ein generisches Restore ist ab dieser Grenze gesperrt."
        )
    return {
        "safe": not blockers,
        "blockers": blockers,
        "active_runner": active_runner or None,
        "legacy_markers": markers,
    }


def restore_original_state(
    adb: AdbClient,
    *,
    timeout: float = DEFAULT_RESTORE_TIMEOUT,
) -> dict[str, Any]:
    before = _restore_preconditions(adb)
    if not before["safe"]:
        raise OriginalStateError(" ".join(before["blockers"]))

    local_hook = _local_hook_path()
    _install_verified_hook(adb, local_hook)

    adb.shell(
        f"'{REMOTE_HELPER}' restore-original --status '{REMOTE_STATUS}'"
    )
    _remove_legacy_artifacts(adb)

    deadline = time.monotonic() + max(0.0, timeout)
    latest = original_state_snapshot(adb)
    while not latest["original_ok"] and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        latest = original_state_snapshot(adb)

    if not latest["original_ok"]:
        raise OriginalStateError(
            "Originalbetrieb wurde freigegeben, aber nicht vollständig bestätigt: "
            + json.dumps(latest["checks"], ensure_ascii=False, sort_keys=True)
        )

    return {
        "ok": True,
        "restored": True,
        "before": before,
        "after": latest,
        "original_ok": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FoxAir original PHNIX runtime check/restore"
    )
    parser.add_argument("--adb", default=shutil.which("adb") or "adb")
    parser.add_argument("--serial")
    parser.add_argument("--timeout", type=float, default=DEFAULT_RESTORE_TIMEOUT)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("action", choices=("check", "restore"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    adb = AdbClient(args.adb, args.serial, env=os.environ.copy())
    try:
        if args.action == "check":
            result = original_state_snapshot(adb)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["original_ok"] else 2
        if not args.execute or args.confirm != RESTORE_CONFIRM_TOKEN:
            raise OriginalStateError(
                f"restore benötigt --execute --confirm {RESTORE_CONFIRM_TOKEN}"
            )
        result = restore_original_state(adb, timeout=args.timeout)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OriginalStateError, TransportError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
