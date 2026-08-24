#!/usr/bin/env python3
"""Small host-side safety layer around the verified PHNIX OTA controller.

PR #1 deliberately does not change the OTA lifecycle after C5A8.  The original
controller remains authoritative for helper hold/cleanup behaviour.  This module
adds only read-only/preflight checks and passive observation:

* free-space preflight for /data and /cache;
* persistent informational host run-state;
* passive C5A8 stall warnings;
* explicit UI distinction between 100 % transport and final OTA completion.

Post-C5A8 disconnect/supervisor/recovery behaviour is intentionally deferred to
a separate follow-up change after real modem process-lifetime tests.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CORE_PATH = HERE / "phnix_local_ota_controller_core.py"
if not CORE_PATH.is_file():
    CORE_PATH = HERE / "phnix_local_ota_controller.py"
if CORE_PATH.resolve() == Path(__file__).resolve():
    raise RuntimeError("hardened controller cannot use itself as core")

_spec = importlib.util.spec_from_file_location("foxair_phnix_ota_core", CORE_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"could not load controller core: {CORE_PATH}")
core = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = core
_spec.loader.exec_module(core)


STORAGE_SAFETY_MARGIN_BYTES = 1024 * 1024
C5A8_STALL_WARNING_SECONDS = 60.0
HOST_RUN_STATE_SCHEMA = "foxair-ota-run-state-v1"


def parse_df_output(output: str, path: str) -> dict[str, object]:
    """Select the last syntactically valid df data row, ignoring headers/noise."""
    for raw_line in reversed(output.splitlines()):
        parts = raw_line.split()
        if len(parts) < 4:
            continue
        try:
            total_kib = int(parts[1])
            used_kib = int(parts[2])
            available_kib = int(parts[3])
        except ValueError:
            continue
        return {
            "filesystem": parts[0],
            "total_bytes": total_kib * 1024,
            "used_bytes": used_kib * 1024,
            "free_bytes": available_kib * 1024,
            "raw": raw_line,
        }
    raise core.OtaError(f"could not parse free storage for {path}: {output!r}")


def remote_filesystem_stat(adb, path: str) -> dict[str, object]:
    """Return filesystem identity and free bytes from BusyBox-compatible df."""
    # Do not rely on a remote shell pipeline such as `tail -n 1`.  The real
    # BusyBox shell supports it, but test transports/simulators may return the
    # command output before pipeline processing.  Parsing belongs on the host.
    output = adb.shell(f"df -k {path} 2>/dev/null")
    return parse_df_output(output, path)


def add_storage_preflight(checks: dict, adb, manifest) -> dict:
    """Fail closed when /data or /cache cannot safely hold the OTA copies."""
    data = remote_filesystem_stat(adb, "/data")
    cache = remote_filesystem_stat(adb, "/cache")
    per_filesystem = manifest.size + STORAGE_SAFETY_MARGIN_BYTES
    same_filesystem = data["filesystem"] == cache["filesystem"]

    if same_filesystem:
        required = manifest.size * 2 + STORAGE_SAFETY_MARGIN_BYTES
        storage_ok = int(data["free_bytes"]) >= required
        requirements = {
            str(data["filesystem"]): {
                "paths": ["/data", "/cache"],
                "free_bytes": data["free_bytes"],
                "required_bytes": required,
            }
        }
    else:
        storage_ok = (
            int(data["free_bytes"]) >= per_filesystem
            and int(cache["free_bytes"]) >= per_filesystem
        )
        requirements = {
            str(data["filesystem"]): {
                "paths": ["/data"],
                "free_bytes": data["free_bytes"],
                "required_bytes": per_filesystem,
            },
            str(cache["filesystem"]): {
                "paths": ["/cache"],
                "free_bytes": cache["free_bytes"],
                "required_bytes": per_filesystem,
            },
        }

    checks["storage_preflight"] = {
        "ok": storage_ok,
        "same_filesystem": same_filesystem,
        "safety_margin_bytes": STORAGE_SAFETY_MARGIN_BYTES,
        "requirements": requirements,
    }
    failures = list(checks.get("failures", []))
    if not storage_ok:
        failures.append("insufficient free storage on /data or /cache for OTA staging/download")
    checks["failures"] = failures
    checks["ok"] = not failures
    return checks


def write_host_run_state(path: Path, **fields) -> None:
    """Persist informational OTA observation state atomically on the host."""
    current: dict[str, object] = {"schema": HOST_RUN_STATE_SCHEMA}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass
    current.update(fields)
    current["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


class RunObserver:
    """Observe core events without changing helper, GDB or board control flow."""

    def __init__(self) -> None:
        self.active = False
        self.manifest = None
        self.state_path: Path | None = None
        self.transfer_started = False
        self.transfer_complete_announced = False
        self.highest_confirmed_offset = 0
        self.last_progress_at = 0.0
        self.last_stall_warning_at = 0.0

    def start(self, manifest) -> None:
        self.active = True
        self.manifest = manifest
        self.state_path = None
        self.transfer_started = False
        self.transfer_complete_announced = False
        self.highest_confirmed_offset = 0
        self.last_progress_at = time.monotonic()
        self.last_stall_warning_at = 0.0

    def stop(self) -> None:
        self.active = False

    def _write(self, **fields) -> None:
        if self.state_path is not None:
            write_host_run_state(self.state_path, **fields)

    def observe(self, event: str, fields: dict) -> None:
        if not self.active:
            return
        now = time.monotonic()

        if event == "state-backed-up":
            directory = fields.get("directory")
            if isinstance(directory, str) and directory:
                self.state_path = Path(directory) / "run-state.json"
                manifest = self.manifest
                self._write(
                    phase="prepared",
                    terminal=False,
                    transfer_started=False,
                    point_of_no_return=False,
                    highest_confirmed_offset=0,
                    software_code=getattr(manifest, "software_code", None),
                    wire_version=getattr(manifest, "wire_version", None),
                    firmware_md5=getattr(manifest, "md5", None),
                    firmware_size=getattr(manifest, "size", None),
                )
            return

        if event != "status":
            return

        hook = fields.get("hook", {})
        info = fields.get("ota_info", {})
        if not isinstance(hook, dict) or not isinstance(info, dict):
            return
        phase = hook.get("phase")
        if not isinstance(phase, str) or not phase:
            phase = "unknown"

        if phase == "c5a8" and not self.transfer_started:
            self.transfer_started = True
            self.last_progress_at = now

        offset = info.get("offset") if info.get("crc_ok") is True else None
        length = info.get("length") if info.get("crc_ok") is True else None
        if isinstance(offset, int) and offset >= self.highest_confirmed_offset:
            if offset > self.highest_confirmed_offset:
                self.highest_confirmed_offset = offset
                self.last_progress_at = now
            if self.transfer_started:
                self._write(
                    phase=phase,
                    transfer_started=True,
                    point_of_no_return=True,
                    highest_confirmed_offset=self.highest_confirmed_offset,
                    ota_length=length,
                )

        if (
            self.transfer_started
            and not self.transfer_complete_announced
            and isinstance(offset, int)
            and isinstance(length, int)
            and length > 0
            and offset >= length
        ):
            self.transfer_complete_announced = True
            _ORIGINAL_PRINT_EVENT("transfer-complete", offset=offset, length=length)
            self._write(
                phase="promotion-observed",
                transfer_started=True,
                point_of_no_return=True,
                highest_confirmed_offset=self.highest_confirmed_offset,
                ota_length=length,
            )

        if (
            self.transfer_started
            and phase == "c5a8"
            and now - self.last_progress_at >= C5A8_STALL_WARNING_SECONDS
            and now - self.last_stall_warning_at >= C5A8_STALL_WARNING_SECONDS
        ):
            self.last_stall_warning_at = now
            _ORIGINAL_PRINT_EVENT(
                "warning",
                message=(
                    "C5A8-Fortschritt seit mindestens 60 Sekunden unveraendert; "
                    "nur passive Warnung, der bestehende OTA-Ablauf wird nicht veraendert"
                ),
                offset=self.highest_confirmed_offset,
                length=length,
            )

        if hook.get("terminal") is True:
            self._write(
                phase=phase,
                terminal=True,
                transfer_started=self.transfer_started,
                point_of_no_return=self.transfer_started,
                highest_confirmed_offset=self.highest_confirmed_offset,
                ota_length=length,
            )


_OBSERVER = RunObserver()
_ORIGINAL_PRINT_EVENT = core.print_event
_ORIGINAL_HUMAN_EVENT = core._human_event
_ORIGINAL_RUN_UPDATE = core.run_update


def _patched_human_event(event: str, fields: dict) -> None:
    if event == "storage-preflight":
        print(core._paint("[OK] Freier Speicher fuer OTA-Staging ausreichend", core.GREEN), flush=True)
        return
    if event == "transfer-complete":
        offset = fields.get("offset")
        length = fields.get("length")
        if isinstance(offset, int) and isinstance(length, int):
            text = (
                f"[..] 100 % Firmware uebertragen ({offset:,} / {length:,} Byte) - "
                "Mainboard kann intern noch programmieren und verifizieren"
            ).replace(",", ".")
        else:
            text = "[..] Firmware uebertragen - Mainboard kann intern noch programmieren und verifizieren"
        print(core._paint(text, core.CYAN), flush=True)
        return
    _ORIGINAL_HUMAN_EVENT(event, fields)


def _observed_print_event(event: str, **fields) -> None:
    _OBSERVER.observe(event, fields)
    _ORIGINAL_PRINT_EVENT(event, **fields)


def run_update(args, adb) -> None:
    """Add host checks/observation, then delegate the OTA lifecycle unchanged."""
    storage = add_storage_preflight({"ok": True, "failures": []}, adb, args.firmware_manifest)
    core.print_event("storage-preflight", **storage["storage_preflight"])
    if not storage["ok"]:
        raise core.OtaError("preflight failed: " + "; ".join(storage["failures"]))

    _OBSERVER.start(args.firmware_manifest)
    try:
        return _ORIGINAL_RUN_UPDATE(args, adb)
    finally:
        _OBSERVER.stop()


core._human_event = _patched_human_event
core.print_event = _observed_print_event
core.run_update = run_update


if __name__ == "__main__":
    raise SystemExit(core.main())
