#!/usr/bin/env python3
"""Conservative safety layer around the verified PHNIX OTA controller.

The underlying controller and its build-specific runtime breakpoints remain
unchanged.  This layer only hardens host-side behaviour around a real full
update: storage preflight, persistent host run-state, passive C5A8 stall
warnings, transfer/promotion UI, and the point-of-no-return rule that the
original phnixIot4G service must never be stopped after C5A8 has started.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
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


def remote_filesystem_stat(adb, path: str) -> dict[str, object]:
    """Return filesystem identity and free bytes using BusyBox-compatible df."""
    line = adb.shell(f"df -k {path} 2>/dev/null | tail -n 1")
    parts = line.split()
    if len(parts) < 4:
        raise core.OtaError(f"could not parse free storage for {path}: {line!r}")
    try:
        free_bytes = int(parts[3]) * 1024
    except ValueError as error:
        raise core.OtaError(f"invalid free storage value for {path}: {parts[3]!r}") from error
    return {"filesystem": parts[0], "free_bytes": free_bytes, "raw": line}


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
    """Persist informational point-of-no-return state atomically on the host."""
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


def remote_transfer_started(adb) -> bool:
    value = adb.shell(
        f"if test -f {core.REMOTE_TRANSFER_STARTED}; then echo STARTED; else echo NOT_STARTED; fi",
        check=False,
    )
    return value.strip() == "STARTED"


def run_update(args, adb) -> None:
    """Hardened copy of the core full-update host loop; board protocol is unchanged."""
    checks = core.preflight(adb, args.firmware, require_helper=False, manifest=args.firmware_manifest)
    checks = add_storage_preflight(checks, adb, args.firmware_manifest)
    checks["local_helper_sha256"] = core.validate_local_runtime_helper(args.runtime_helper)
    core.print_event("preflight", **checks)
    if not checks["ok"]:
        raise core.OtaError("preflight failed: " + "; ".join(checks["failures"]))
    if not args.execute:
        core.print_event("dry-run-complete", message="No modem or bus state was changed")
        return

    simulated = adb.shell(f"test -f {core.REMOTE_SIM_MARKER}; echo $?") == "0"
    expected_confirm = "VM-FULL-UPDATE" if simulated else "PHNIX-FULL-UPDATE"
    if args.confirm != expected_confirm:
        raise core.OtaError(f"confirmation must be {expected_confirm}")
    core.install_runtime_helper(adb, args.runtime_helper)

    run_state_path: Path | None = None
    try:
        state_dir = args.state_dir / time.strftime("%Y%m%d-%H%M%S")
        core.save_remote_state(adb, state_dir)
        run_state_path = state_dir / "run-state.json"
        write_host_run_state(
            run_state_path,
            phase="prepared",
            transfer_started=False,
            point_of_no_return=False,
            highest_confirmed_offset=0,
            software_code=args.firmware_manifest.software_code,
            wire_version=args.firmware_manifest.wire_version,
            firmware_md5=args.firmware_manifest.md5,
            firmware_size=args.firmware_manifest.size,
        )
        core.print_event("state-backed-up", directory=str(state_dir))
        core.stage_firmware(adb, args.firmware, args.firmware_manifest)

        payload = core.command_payload(args.firmware_url, args.firmware_manifest)
        with tempfile.TemporaryDirectory() as temp_dir:
            command_file = Path(temp_dir) / "ota-command.json"
            command_file.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            adb.push(command_file, core.REMOTE_COMMAND)
    except BaseException:
        core.remove_local_ota_artifacts(adb, remove_helper=True)
        raise

    helper_command = (
        f"{core.REMOTE_HELPER} run --build-id {core.EXPECTED_BUILD_ID} "
        f"--command {core.REMOTE_COMMAND} --status {core.REMOTE_STATUS} "
        "--allow-publish 0023,0053,0083"
    )
    adb.shell(f"rm -f {core.REMOTE_STATUS}")
    core.print_event("hook-start", allowed_publish=["0023", "0053", "0083"])
    helper = adb.popen_shell(helper_command)

    phase_started = time.monotonic()
    previous_phase = None
    last_offset = -1
    highest_confirmed_offset = 0
    last_progress_at = time.monotonic()
    last_stall_warning_at = 0.0
    transfer_started = False
    transfer_complete_announced = False
    safe_terminal = False
    guarded_hold = False
    helper_exit_seen_at = None
    try:
        while True:
            status = core.remote_status(adb, allow_transient_info=True)
            hook = status["hook"]
            info = status["ota_info"]
            core.print_event("status", **status)
            now = time.monotonic()

            phase = hook.get("phase", "unknown")
            if phase != previous_phase:
                previous_phase = phase
                phase_started = now
                core.print_event("phase-change", phase=phase)

            if phase == "c5a8" and not transfer_started:
                transfer_started = True
                last_progress_at = now
                if run_state_path is not None:
                    write_host_run_state(
                        run_state_path,
                        phase="c5a8",
                        transfer_started=True,
                        point_of_no_return=True,
                    )

            observed_offset = info.get("offset") if info.get("crc_ok") is True else None
            observed_length = info.get("length") if info.get("crc_ok") is True else None
            if isinstance(observed_offset, int) and observed_offset != last_offset:
                last_offset = observed_offset
                if transfer_started and observed_offset >= highest_confirmed_offset:
                    highest_confirmed_offset = observed_offset
                    last_progress_at = now
                    if run_state_path is not None:
                        write_host_run_state(
                            run_state_path,
                            phase=phase,
                            transfer_started=True,
                            point_of_no_return=True,
                            highest_confirmed_offset=highest_confirmed_offset,
                            ota_length=observed_length,
                        )

            if (
                transfer_started
                and not transfer_complete_announced
                and isinstance(observed_offset, int)
                and isinstance(observed_length, int)
                and observed_length > 0
                and observed_offset >= observed_length
            ):
                transfer_complete_announced = True
                core.print_event("transfer-complete", offset=observed_offset, length=observed_length)
                if run_state_path is not None:
                    write_host_run_state(
                        run_state_path,
                        phase="promotion",
                        transfer_started=True,
                        point_of_no_return=True,
                        highest_confirmed_offset=highest_confirmed_offset,
                        ota_length=observed_length,
                    )

            if (
                transfer_started
                and phase == "c5a8"
                and now - last_progress_at >= C5A8_STALL_WARNING_SECONDS
                and now - last_stall_warning_at >= C5A8_STALL_WARNING_SECONDS
            ):
                last_stall_warning_at = now
                core.print_event(
                    "warning",
                    message=(
                        "C5A8-Fortschritt seit mindestens 60 Sekunden unveraendert; "
                        "Originaldienst laeuft weiter, kein automatischer Eingriff"
                    ),
                    offset=highest_confirmed_offset,
                    length=observed_length,
                )

            if hook.get("terminal") is True:
                safe_terminal = phase in {
                    "success", "failed", "parser-rejected", "precondition-rejected",
                    "same-version",
                }
                if run_state_path is not None:
                    write_host_run_state(
                        run_state_path,
                        phase=phase,
                        terminal=True,
                        transfer_started=transfer_started,
                        point_of_no_return=transfer_started,
                        highest_confirmed_offset=highest_confirmed_offset,
                    )
                if phase == "success":
                    if hook.get("board_ota_step") != 12:
                        safe_terminal = False
                        raise core.OtaError("success was reported without confirmed board_ota_step 12")
                    core.print_event("complete", offset=info.get("offset"), length=info.get("length"))
                    return
                if phase == "same-version":
                    core.print_event(
                        "warning",
                        message="Gleiche Firmware erkannt - keine Firmwaredaten uebertragen",
                    )
                    return
                raise core.OtaError(f"terminal OTA state: {phase}")

            if helper.poll() is not None:
                if helper_exit_seen_at is None:
                    helper_exit_seen_at = now
                if now - helper_exit_seen_at < 1.0:
                    time.sleep(args.poll_interval)
                    continue
                raise core.OtaError(f"runtime helper exited unexpectedly with code {helper.returncode}")

            if phase == "c5a8":
                time.sleep(args.poll_interval)
                continue
            phase_limit = {
                "c350": args.handshake_timeout,
                "c357": args.handshake_timeout,
            }.get(phase, args.start_timeout)
            if now - phase_started > phase_limit:
                raise core.OtaError(f"phase watchdog expired in {phase}")
            time.sleep(args.poll_interval)
    except BaseException as error:
        if not safe_terminal:
            started = transfer_started
            if not started:
                try:
                    started = remote_transfer_started(adb)
                except BaseException:
                    started = False
            if started:
                transfer_started = True
                if run_state_path is not None:
                    write_host_run_state(
                        run_state_path,
                        phase="host-supervision-lost",
                        terminal=False,
                        transfer_started=True,
                        point_of_no_return=True,
                        highest_confirmed_offset=highest_confirmed_offset,
                        error=str(error),
                    )
                core.print_event(
                    "warning",
                    message=(
                        "Host/ADB-Ueberwachung nach begonnenem C5A8 verloren; "
                        "der originale phnixIot4G-Dienst wird nicht angehalten"
                    ),
                )
            else:
                adb.shell(f"{core.REMOTE_HELPER} hold --status {core.REMOTE_STATUS}", check=False)
                guarded_hold = True
                core.print_event(
                    "guarded-hold",
                    message="Active OTA was frozen fail-closed; cloud and watchdog guards remain active",
                )
        raise
    finally:
        if safe_terminal and helper.poll() is None:
            adb.shell(f"{core.REMOTE_HELPER} stop --status {core.REMOTE_STATUS}", check=False)
            try:
                helper.wait(timeout=10)
            except subprocess.TimeoutExpired:
                core.print_event("warning", message="runtime helper did not exit within 10 seconds")
        if safe_terminal:
            core.remove_local_ota_artifacts(adb, remove_helper=True)
            core.print_event("hook-stopped")
            runtime = core.verify_original_runtime(adb)
            if not runtime["ok"]:
                raise core.OtaError(f"original LTE runtime was not fully restored: {runtime}")
            core.print_event("services-restored", **runtime)
        elif guarded_hold:
            core.print_event("manual-recovery-required", status=core.REMOTE_STATUS)


def _patched_human_event(event: str, fields: dict) -> None:
    if event == "transfer-complete":
        offset = fields.get("offset")
        length = fields.get("length")
        if isinstance(offset, int) and isinstance(length, int):
            text = (
                f"[..] 100 % Firmware uebertragen ({offset:,} / {length:,} Byte) - "
                "Mainboard programmiert und verifiziert intern weiter"
            ).replace(",", ".")
        else:
            text = "[..] Firmware uebertragen - Mainboard programmiert und verifiziert intern weiter"
        print(core._paint(text, core.CYAN), flush=True)
        return
    _ORIGINAL_HUMAN_EVENT(event, fields)


_ORIGINAL_HUMAN_EVENT = core._human_event
core._human_event = _patched_human_event
core.run_update = run_update


if __name__ == "__main__":
    raise SystemExit(core.main())
