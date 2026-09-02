"""Fail-closed removal of FoxAir Updater working files from a DTU.

This intentionally removes only files/directories created by our updater tooling.
Original PHNIX files such as phnixIot4G, phnixIot_device_OTA,
phnixIot_device_OTA_INFO and phnixIot_device_statisic are never touched.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

for candidate in (Path(__file__).resolve().parents[2], Path.cwd()):
    if (candidate / "updater/common/adb_transport.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from updater.common.adb_transport import AdbClient, TransportError


CONFIRM_TOKEN = "FOXAIR-DTU-CLEAN"
REMOTE_BASE = "/data/foxair_ota_runner"
STATUS_SCHEMA = "foxair-dtu-ota-run-v1"
REMOTE_INFO = "/data/phnixIot_device_OTA_INFO"

# Only updater-owned artifacts. Never add original PHNIX state/data here.
CLEAN_PATHS = (
    "/data/foxair_ota_runner",
    "/data/phnix_ota_runtime_hook",
    "/data/.phnix_ota_runtime_hook.new",
    "/data/phnix_local_ota",
    "/tmp/phnix_ota_status.json",
    "/tmp/phnix_ota_httpd.pid",
    "/tmp/phnix_ota_hook",
    "/tmp/phnix_handshake_trace.json",
)

LEGACY_HOOK_STATE = "/tmp/phnix_ota_hook"


class CleanupError(RuntimeError):
    pass


def _exists(adb: AdbClient, path: str) -> bool:
    return adb.shell(f"test -e '{path}' && echo 1 || true") == "1"


def _read(adb: AdbClient, path: str) -> str:
    return adb.shell(f"cat '{path}' 2>/dev/null || true")


def _process_lines(adb: AdbClient) -> list[str]:
    # Bracketed expressions keep grep/the shell itself out of the result. Any
    # matching process blocks cleanup, even when a lock/marker went stale or
    # disappeared: process evidence wins over bookkeeping.
    raw = adb.shell(
        "ps 2>/dev/null | grep -E "
        "'([d]tu_ota_supervisor|[p]hnix_ota_runtime_hook|[r]untime_hook|"
        "[p]hnix_local_ota|[g]db(server)?)' || true"
    )
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _ota_info_resume(adb: AdbClient) -> dict[str, object]:
    """Read only the resume counters from the original 220-byte OTA_INFO.

    The file itself is never modified here.  Unknown/corrupt state is a blocker
    because cleanup must never guess that an OTA is idle.
    """
    raw = adb.read_file(REMOTE_INFO)
    if len(raw) != 220:
        return {"valid": False, "length_bytes": len(raw), "offset": None, "length": None}
    return {
        "valid": True,
        "length_bytes": 220,
        "offset": int.from_bytes(raw[212:216], "little"),
        "length": int.from_bytes(raw[216:220], "little"),
    }


def safety_snapshot(adb: AdbClient) -> dict[str, object]:
    blockers: list[str] = []
    notes: list[str] = []

    active_lock = _read(adb, f"{REMOTE_BASE}/active.lock/run_id").strip()
    if active_lock:
        raw = _read(adb, f"{REMOTE_BASE}/runs/{active_lock}/status.json")
        try:
            status = json.loads(raw)
        except json.JSONDecodeError:
            blockers.append(f"Aktiver Runner-Lock {active_lock} hat keinen gültigen Status.")
        else:
            if (
                not isinstance(status, dict)
                or status.get("schema") != STATUS_SCHEMA
                or status.get("run_id") != active_lock
            ):
                blockers.append(f"Aktiver Runner-Lock {active_lock} ist inkonsistent.")
            elif status.get("terminal") is not True:
                blockers.append(
                    f"DTU-OTA-Lauf {active_lock} ist noch aktiv "
                    f"(phase={status.get('phase', '?')})."
                )
            else:
                notes.append(f"Staler terminaler Runner-Lock: {active_lock}")

    legacy_markers = {
        "run_active": _exists(adb, f"{LEGACY_HOOK_STATE}/run.active"),
        "transfer_started": _exists(adb, f"{LEGACY_HOOK_STATE}/transfer-started"),
        "injection_started": _exists(adb, f"{LEGACY_HOOK_STATE}/injection-started"),
        "original_service_owns": _exists(adb, f"{LEGACY_HOOK_STATE}/original-service-owns"),
    }
    processes = _process_lines(adb)
    if processes:
        blockers.append(
            "OTA-/Debugger-Hilfsprozesse laufen noch: " + " | ".join(processes)
        )

    if legacy_markers["transfer_started"]:
        blockers.append("Legacy-OTA markiert bereits begonnene Firmwareübertragung.")
    if legacy_markers["injection_started"]:
        blockers.append("Legacy-OTA markiert eine laufende Parser-Injektion.")
    if legacy_markers["original_service_owns"]:
        blockers.append("Legacy-OTA ist noch an den Originaldienst übergeben.")
    if legacy_markers["run_active"] and processes:
        blockers.append("Legacy-OTA ist als aktiv markiert und OTA-Hilfsprozesse laufen noch.")
    elif legacy_markers["run_active"]:
        notes.append("Staler Legacy-run.active-Marker ohne laufenden OTA-Hilfsprozess.")

    try:
        ota_info = _ota_info_resume(adb)
    except (TransportError, OSError, ValueError) as error:
        ota_info = {"valid": False, "error": str(error), "offset": None, "length": None}
        blockers.append("OTA_INFO konnte nicht sicher gelesen werden.")
    else:
        if ota_info.get("valid") is not True:
            blockers.append(
                "OTA_INFO hat nicht die erwarteten 220 Byte; OTA-Ruhezustand ist nicht beweisbar."
            )
        elif ota_info.get("offset") != 0 or ota_info.get("length") != 0:
            blockers.append(
                "OTA_INFO enthält einen aktiven/fortsetzbaren OTA-Zustand "
                f"(offset={ota_info.get('offset')}, length={ota_info.get('length')})."
            )

    present = [path for path in CLEAN_PATHS if _exists(adb, path)]
    return {
        "safe": not blockers,
        "blockers": blockers,
        "notes": notes,
        "active_lock": active_lock or None,
        "legacy_markers": legacy_markers,
        "ota_helper_processes": processes,
        "ota_info": ota_info,
        "present": present,
    }


def clean(adb: AdbClient) -> dict[str, object]:
    before = safety_snapshot(adb)
    if not before["safe"]:
        raise CleanupError("Bereinigung gesperrt: " + " ".join(before["blockers"]))

    for path in CLEAN_PATHS:
        adb.shell(f"rm -rf '{path}'")

    remaining = [path for path in CLEAN_PATHS if _exists(adb, path)]
    if remaining:
        raise CleanupError("Bereinigung unvollständig; noch vorhanden: " + ", ".join(remaining))

    return {
        "ok": True,
        "cleaned": list(CLEAN_PATHS),
        "remaining": [],
        "before": before,
        "original_phnix_files_touched": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FoxAir-Updater-Dateien sicher von einer DTU entfernen")
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("action", choices=("check", "clean"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = os.environ.copy()
    adb = AdbClient(args.adb, env=env)
    try:
        snapshot = safety_snapshot(adb)
        if args.action == "check":
            print(json.dumps({"ok": snapshot["safe"], **snapshot}, ensure_ascii=False))
            return 0 if snapshot["safe"] else 2
        if not args.execute or args.confirm != CONFIRM_TOKEN:
            raise CleanupError(
                f"clean benötigt --execute --confirm {CONFIRM_TOKEN}"
            )
        result = clean(adb)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (CleanupError, TransportError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())