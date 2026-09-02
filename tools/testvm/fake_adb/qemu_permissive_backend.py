#!/usr/bin/env python3
"""Permissive ADB backend for the isolated FoxAir TestVM.

The original ARM ``phnixIot4G`` process, /data, /cache and the Work RS485 lab
remain authoritative.  Unknown ADB shell commands are executed as root in a
private mount namespace.  The build-specific production runtime hook is the one
exception: it relies on attaching gdbserver to a real ARM process, which does
not map to qemu-user host PIDs.  Its updater-facing state machine is therefore
handled by the repository's deterministic PHNIX simulator while its files and
OTA_INFO are mapped back into the same QEMU/ADB device namespace.
"""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import ModuleType

HERE = Path(__file__).resolve().parent
WORK_BACKEND = HERE / "qemu_work_lab_backend.py"
RUNTIME_SIMULATOR = HERE / "phnix_ota_simulator.py"
if not RUNTIME_SIMULATOR.is_file():
    # In an installed VM the installer places the simulator beside this
    # backend.  In a source checkout keep tests/imports usable without a
    # generated duplicate file.
    RUNTIME_SIMULATOR = HERE.parents[1] / "phnix_ota/phnix_ota_simulator.py"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Modul nicht ladbar: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


work = _load_module(WORK_BACKEND, "foxair_work_qemu_permissive_base")
runtime_sim = _load_module(RUNTIME_SIMULATOR, "foxair_qemu_runtime_simulator")

sim_home = work.sim_home
reset_state = work.reset_state
service_pids = work.service_pids
qemu_rootfs = work.qemu_rootfs
lab_root = work.lab_root
scenario_state = work.scenario_state
apply_control = work.apply_control
service_info = work.service_info
ensure_service_watchdog = work.ensure_service_watchdog


def _state_root() -> Path:
    return Path(os.environ.get("FOXAIR_FAKE_ADB_STATE", "/var/lib/foxair-fake-adb"))


def device_tmp() -> Path:
    path = Path(os.environ.get("FOXAIR_FAKE_ADB_TMP", str(_state_root() / "device-tmp")))
    path.mkdir(parents=True, exist_ok=True)
    return path


def root_path(remote: str) -> Path:
    """Map ADB file/SYNC paths into the virtual LTE device namespace."""
    if not remote.startswith("/"):
        raise ValueError("Nur absolute Remote-Pfade werden unterstützt")
    if remote == "/tmp":
        return device_tmp()
    if remote.startswith("/tmp/"):
        relative = Path(remote).relative_to("/tmp")
        candidate = device_tmp() / relative
        parent = candidate.parent.resolve()
        root = device_tmp().resolve()
        if parent != root and root not in parent.parents:
            raise ValueError("Remote-/tmp-Pfad verlässt den ADB-Tempbereich")
        return candidate
    return work.root_path(remote)


def _runtime_sim_home() -> Path:
    return _state_root() / "runtime-sim"


# Re-use the already tested OTA state machine, but never its separate fake
# rootfs. Every remote file it touches is redirected to the QEMU/ADB namespace.
runtime_sim.sim_home = _runtime_sim_home
runtime_sim.root_path = root_path
_original_set_status = runtime_sim.set_status


def _mirrored_set_status(phase: str, terminal: bool = False, **extra) -> None:
    hook = root_path("/tmp/phnix_ota_hook")
    hook.mkdir(parents=True, exist_ok=True)
    if phase in {"parser-injection", "accepted", "c350", "c357", "c5a8"}:
        (hook / "injection-started").touch()
    if phase == "c5a8":
        (hook / "transfer-started").touch()
    _original_set_status(phase, terminal, **extra)


runtime_sim.set_status = _mirrored_set_status


def _runtime_sim_prepare() -> None:
    """Mirror the active Work scenario into the deterministic hook state machine."""
    home = _runtime_sim_home()
    home.mkdir(parents=True, exist_ok=True)
    state = scenario_state()
    config = {
        "scenario": state.get("scenario", "success"),
        "cancel_scenario": state.get("cancel_scenario", "success"),
        "handshake_scenario": state.get("handshake_scenario", "success"),
        "same_version_scenario": state.get("same_version_scenario", "success"),
    }
    if config["scenario"] not in runtime_sim.SCENARIOS:
        config["scenario"] = "success"
    if config["cancel_scenario"] not in runtime_sim.CANCEL_SCENARIOS:
        config["cancel_scenario"] = "success"
    if config["handshake_scenario"] not in runtime_sim.HANDSHAKE_SCENARIOS:
        config["handshake_scenario"] = "success"
    if config["same_version_scenario"] not in runtime_sim.SAME_VERSION_SCENARIOS:
        config["same_version_scenario"] = "success"
    runtime_sim.write_json(home / "config.json", config)
    runtime = home / "runtime.json"
    if not runtime.exists():
        runtime_sim.write_json(runtime, {
            "running": False,
            "httpd": False,
            "held": False,
            "cloud_blocked": False,
            "watchdogs_paused": False,
            "recovery_running": False,
        })


def _cleanup_runtime_markers() -> None:
    hook = root_path("/tmp/phnix_ota_hook")
    for name in ("run.active", "safe-to-clean", "transfer-started", "injection-started"):
        (hook / name).unlink(missing_ok=True)


def _real_ota_status(phase: str, terminal: bool = False, **extra) -> None:
    _mirrored_set_status(phase, terminal, **extra)


def _original_ota_run(command: str) -> tuple[int, bytes]:
    """Bridge the production helper call to the original ARM OTA path."""
    state = scenario_state()
    scenario = state.get("scenario", "success")
    hook = root_path("/tmp/phnix_ota_hook")
    hook.mkdir(parents=True, exist_ok=True)
    (hook / "run.active").touch()
    stop_request = hook / "stop-requested"
    stop_request.unlink(missing_ok=True)

    expected_size = 0
    offered_wire_version = ""
    argv = shlex.split(command)
    isolate_mqtt = "--isolate-mqtt" in argv
    runtime_sim.runtime_state(
        running=True, cloud_blocked=isolate_mqtt,
        watchdogs_paused=True, held=False,
    )
    command_path = None
    for index, item in enumerate(argv[:-1]):
        if item == "--command":
            command_path = root_path(argv[index + 1])
            break
    if command_path is not None and command_path.exists():
        try:
            request = json.loads(command_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return 2, f"ungueltige OTA-Kommandodatei: {exc}\n".encode()
        param = request.get("param") if isinstance(request.get("param"), dict) else {}
        display_version = str(param.get("softwareVer", ""))
        version_digits = "".join(ch for ch in display_version if ch.isdigit())
        offered_wire_version = version_digits.zfill(4)
        expected_size = int(param.get("fileSize", -1))
        expected_md5 = str(param.get("fileMD5", "")).upper()
        expected = (
            request.get("cmd") == "CMD_OTA"
            and str(request.get("code")) == "0033"
            and str(param.get("softwareCode")) == "82400644"
            and len(offered_wire_version) == 4
            and str(param.get("ssid")) == "0063"
            and len(expected_md5) == 32
            and expected_size > 0
        )
        firmware = root_path("/data/phnix_local_ota/phnixIot_device_OTA.bin")
        try:
            firmware_bytes = firmware.read_bytes()
        except OSError:
            firmware_bytes = b""
        expected = expected and (
            len(firmware_bytes) == expected_size
            and hashlib.md5(firmware_bytes).hexdigest().upper() == expected_md5
        )
        if not expected:
            return 2, b"Original-QEMU-OTA: Kommandodaten und bereitgestellte Firmware stimmen nicht ueberein\n"
        try:
            # The original parser buffer is 232 bytes. The Work-Lab HTTP stub
            # exposes the historical suffix-free endpoint, which fits while
            # preserving all firmware identity fields unchanged.
            injected_request = json.loads(json.dumps(request))
            injected_request["param"]["otaFileDownloadAddr"] = (
                "http://127.0.0.1:8081/phnixIot_device_OTA"
            )
            work.set_original_ota_json(json.dumps(injected_request, separators=(",", ":")))
        except (UnicodeEncodeError, ValueError) as exc:
            return 2, f"OTA-Kommandodatei nicht injizierbar: {exc}\n".encode()

    _real_ota_status("waiting-for-yield-loop", armed=True, active=False, original_service=True)
    startup_done = threading.Event()

    def startup_heartbeat() -> None:
        # Starting the imported ARM runtime can take about a minute and one
        # safe pre-C350 retry can take longer. Alternate honest non-terminal
        # startup phases so the production controller's per-phase watchdog
        # observes progress instead of aborting a still-safe VM-only startup.
        phases = ("attaching", "board-initialization")
        index = 0
        while not startup_done.wait(25.0):
            _real_ota_status(
                phases[index % len(phases)], armed=True, active=False,
                original_service=True,
            )
            index += 1

    heartbeat = threading.Thread(target=startup_heartbeat, daemon=True)
    heartbeat.start()
    try:
        ok, message, run_dir = work.start_original_ota(scenario)
    finally:
        startup_done.set()
        heartbeat.join(timeout=1.0)
    if not ok or run_dir is None:
        _real_ota_status("failed", True, recovery_required=True, error=message)
        return 1, (message + "\n").encode()

    transcript = run_dir / "ttyHSL2-transcript.txt"
    gdb_log = run_dir / "gdb-local-ota-handler.log"
    try:
        runner_meta = json.loads(work._runner_meta().read_text(encoding="utf-8"))
        transcript_offset = int(runner_meta.get("ota_transcript_offset", 0))
        gdb_offset = int(runner_meta.get("ota_gdb_offset", 0))
    except (OSError, ValueError, json.JSONDecodeError):
        transcript_offset = gdb_offset = 0
    seen_c350 = seen_c357 = seen_c5a8 = False
    seen_attaching = seen_injection = seen_accepted = False
    seen_transfer_complete = seen_staging_verified = False
    seen_promotion = seen_promotion_committed = False
    wait_stage = 0
    restart_at_half_done = False
    monitor_started = time.monotonic()
    deadline = time.monotonic() + max(10, work.DEFAULT_RUN_SECONDS)

    def restart_idle_original() -> tuple[bool, str]:
        _real_ota_status(
            "restoring-original", armed=False, active=False,
            original_service=True,
        )
        restore_done = threading.Event()

        def restore_heartbeat() -> None:
            phases = ("restoring-original", "attaching")
            index = 0
            while not restore_done.wait(25.0):
                _real_ota_status(
                    phases[index % len(phases)], armed=False, active=False,
                    original_service=True,
                )
                index += 1

        thread = threading.Thread(target=restore_heartbeat, daemon=True)
        thread.start()
        try:
            return work._start_runner(
                "scenario", scenario_state().get("scenario", "success")
            )
        finally:
            restore_done.set()
            thread.join(timeout=1.0)

    while time.monotonic() < deadline:
        if stop_request.exists():
            work.stop_runner()
            _real_ota_status("guarded-hold", True, recovery_required=True)
            return 1, b"original OTA stopped in guarded hold\n"
        try:
            trace = transcript.read_bytes()[transcript_offset:].decode("utf-8", errors="replace")
        except OSError:
            trace = ""
        try:
            debugger_trace = gdb_log.read_bytes()[gdb_offset:].decode("utf-8", errors="replace")
        except OSError:
            debugger_trace = ""
        runner_pid = work._read_runner_pid()
        if runner_pid is None and not any((seen_c350, seen_c357, seen_c5a8)):
            error = "QEMU/GDB OTA runner exited before C350"
            if debugger_trace:
                error += ": " + debugger_trace.strip().splitlines()[-1]
            _real_ota_status("failed", True, recovery_required=True, error=error)
            return 1, (error + "\n").encode("utf-8")
        if (
            not seen_attaching
            and not any((seen_c350, seen_c357, seen_c5a8))
            and time.monotonic() - monitor_started >= 25
        ):
            seen_attaching = True
            _real_ota_status("attaching", armed=True, active=False, original_service=True)
        if not seen_injection and "FOXAIR_OTA_INJECT" in debugger_trace:
            seen_injection = True
            (hook / "injection-started").touch()
            _real_ota_status("parser-injection", armed=True, active=False, original_service=True)
        if not seen_accepted and "FOXAIR_OTA_POST_PARSER" in debugger_trace:
            seen_accepted = True
            _real_ota_status("accepted", armed=True, active=True, original_service=True)
        elapsed = time.monotonic() - monitor_started
        if not seen_c350 and wait_stage == 0 and elapsed >= 75:
            wait_stage = 1
            _real_ota_status("waiting-for-board-ready", armed=True, active=True, original_service=True)
        if not seen_c350 and wait_stage == 1 and elapsed >= 125:
            wait_stage = 2
            _real_ota_status("board-initialization", armed=True, active=True, original_service=True)
        if not seen_c350 and "c350-minimal-confirm" in trace:
            seen_c350 = True
            _real_ota_status("c350", c350_sent=True, original_service=True)
        if "c36e-status-0" in trace:
            restarted, restart_message = restart_idle_original()
            if not restarted:
                _real_ota_status(
                    "failed", True, recovery_required=True,
                    error="Leerlaufdienst nach Same-Version nicht startbar: " + restart_message,
                )
                return 1, (restart_message + "\n").encode("utf-8")
            _real_ota_status(
                "same-version", True, c36e_status=0, c350_sent=True,
                c357_sent=False, c5a8_sent=False, state_restored=True,
                recovery_required=False, original_service=True,
            )
            _cleanup_runtime_markers()
            runtime_sim.runtime_state(
                running=False, cloud_blocked=False,
                watchdogs_paused=False, held=False,
            )
            return 0, b"original service reported same version\n"
        if not seen_c357 and "c357-minimal-confirm" in trace:
            seen_c357 = True
            _real_ota_status("c357", c350_sent=True, c357_sent=True, original_service=True)
        if not seen_c5a8 and "DTU -> BOARD 63 10 c5 a8" in trace:
            seen_c5a8 = True
            (hook / "transfer-started").touch()
            _real_ota_status("c5a8", c5a8_sent=True, original_service=True)
        if scenario == "restart-at-50-resume" and seen_c5a8 and not restart_at_half_done:
            try:
                raw_info = root_path("/data/phnixIot_device_OTA_INFO").read_bytes()
                confirmed_offset = int.from_bytes(raw_info[212:216], "little")
                image_length = int.from_bytes(raw_info[216:220], "little")
            except OSError:
                confirmed_offset = image_length = 0
            if image_length > 0 and confirmed_offset * 2 >= image_length:
                restart_at_half_done = True
                _real_ota_status(
                    "c5a8", c5a8_sent=True, original_service=False,
                    simulated_lte_restart=True, resume_offset=confirmed_offset,
                )
                (sim_home() / "started").unlink(missing_ok=True)
                work.stop_runner()
                time.sleep(5.0)
                resumed, resume_message = work._start_runner(
                    "scenario", "restart-at-50-resume", original_ota=False
                )
                if not resumed:
                    (sim_home() / "started").touch()
                    error = "simulierter LTE-Resume fehlgeschlagen: " + resume_message
                    _real_ota_status("failed", True, recovery_required=True, error=error)
                    return 1, (error + "\n").encode("utf-8")
                (sim_home() / "started").touch()
                try:
                    resumed_meta = json.loads(work._runner_meta().read_text(encoding="utf-8"))
                    run_dir = Path(resumed_meta["run_dir"])
                except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
                    error = f"Resume-Run-Verzeichnis fehlt: {exc}"
                    _real_ota_status("failed", True, recovery_required=True, error=error)
                    return 1, (error + "\n").encode("utf-8")
                transcript = run_dir / "ttyHSL2-transcript.txt"
                gdb_log = run_dir / "gdb-local-ota-handler.log"
                transcript_offset = gdb_offset = 0
                _real_ota_status(
                    "c5a8", c5a8_sent=True, original_service=True,
                    resume_active=True, resume_offset=confirmed_offset,
                )
                continue
        if not seen_transfer_complete and "VERIFIED transfer-complete bytes=" in trace:
            seen_transfer_complete = True
            _real_ota_status(
                "transfer-complete", c5a8_sent=True, transfer_verified=True,
                transferred_bytes=expected_size, expected_bytes=expected_size,
                original_service=True,
            )
        if not seen_staging_verified and "BOARD -> DTU c36e-status-3" in trace:
            seen_staging_verified = True
            _real_ota_status(
                "staging-verified", c5a8_sent=True, transfer_verified=True,
                staging_md5_verified=True, original_service=True,
            )
        if not seen_promotion and "PHASE promotion-start" in trace:
            seen_promotion = True
            _real_ota_status(
                "promotion", c5a8_sent=True, transfer_verified=True,
                physical_flash_simulated=True, original_service=True,
            )
        if "VERIFIED promotion status=5 acked" in trace:
            if not seen_promotion_committed:
                seen_promotion_committed = True
                _real_ota_status(
                    "promotion-committed", c5a8_sent=True,
                    transfer_verified=True, staging_md5_verified=True,
                    target_md5_verified=True, commit_verified=True,
                    physical_flash_simulated=True, original_service=True,
                )
                time.sleep(2.0)
            updated_state = scenario_state()
            updated_state["board_version"] = offered_wire_version
            work.base._write_scenario_state(updated_state)
            # The real V3.4 trace and process-age evidence show phnixIot4G
            # returning to OTA step 12 in the same process after status 5.
            # Keep this original ARM/QEMU run alive.  Starting a fresh idle
            # runner here produced a second `set /dev/ttyGS0` initialization
            # that belongs only to the simulator lifecycle, not to the board
            # completion protocol.
            # The original service has correctly cleared OTA_INFO by now. Keep
            # one CRC-valid VM-only completion snapshot until the controller
            # consumes the terminal status; its normal cleanup restores the
            # original empty record immediately afterwards.
            info_path = root_path("/data/phnixIot_device_OTA_INFO")
            try:
                completed_info = bytearray(info_path.read_bytes())
            except OSError:
                completed_info = bytearray(220)
            if len(completed_info) != 220:
                completed_info = bytearray(220)
            completed_info[212:216] = expected_size.to_bytes(4, "little")
            completed_info[216:220] = expected_size.to_bytes(4, "little")
            completed_info[:4] = runtime_sim.crc16_x25(completed_info[4:]).to_bytes(4, "little")
            info_path.write_bytes(completed_info)
            _real_ota_status(
                "success", True, board_ota_step=12, c5a8_sent=True,
                transfer_verified=True, physical_flash_simulated=True,
                completed_offset=expected_size, completed_length=expected_size,
                original_service=True, recovery_required=False,
            )
            _cleanup_runtime_markers()
            runtime_sim.runtime_state(
                running=False, cloud_blocked=False,
                watchdogs_paused=False, held=False,
            )
            return 0, b"original service transfer verified; board promotion simulated\n"
        time.sleep(0.2)
    _real_ota_status("failed", True, recovery_required=True, error="VM OTA timeout")
    return 1, b"original OTA timed out\n"


def _runtime_helper_shell(command: str) -> tuple[int, bytes]:
    _runtime_sim_prepare()
    hook = root_path("/tmp/phnix_ota_hook")
    hook.mkdir(parents=True, exist_ok=True)
    action = command.split()[1] if len(command.split()) > 1 else ""
    if action == "run":
        return _original_ota_run(command)
    if action == "hold":
        (hook / "stop-requested").touch()
        return 0, b"guarded hold requested\n"
    if action in {"run", "same-version-probe", "handshake-probe", "cancel", "cancel-probe"}:
        (hook / "run.active").touch()
    code, output = runtime_sim.shell(command)
    if action in {"stop", "restore-original"}:
        (hook / "stop-requested").unlink(missing_ok=True)
        _cleanup_runtime_markers()
        # The deterministic helper may already have removed run.active after
        # writing a safe terminal record, in which case its generic stop path
        # returns non-zero.  That is not a failed restore: the simulated modem
        # supervisor must still recreate the idle original service.  Success
        # is therefore determined by the runner restart, not by the stale
        # helper marker.
        scenario = scenario_state().get("scenario", "success")
        restarted, message = work.apply_control("scenario", scenario)
        if not restarted:
            return 1, output + (
                "VM-Originaldienst konnte nicht neu gestartet werden: "
                + message + "\n"
            ).encode("utf-8")
        code = 0
        output += (message + "\n").encode("utf-8")
    elif action in {"run", "same-version-probe"}:
        status_path = root_path("/tmp/phnix_ota_status.json")
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            status = {}
        if status.get("terminal") is True and status.get("recovery_required") is not True:
            _cleanup_runtime_markers()
    return code, output


def _phnix_special(command: str) -> bool:
    command = command.strip()
    return (
        command in {"pidof phnixIot4G || true", "pidof phnixIot4G", "pidof gdbserver gdb || true"}
        or command.startswith("p=$(pidof phnixIot4G")
        or (command.startswith("ps | awk") and "{helloworld}" in command)
        or (re.match(r"netstat -(?:nt|tn)\b", command) is not None and ":1883" in command)
        or command.startswith("killall") and "phnixIot4G" in command
        or command.startswith("kill -STOP ")
        or command.startswith("kill -CONT ")
        or command.startswith("kill -TERM ")
        or command.startswith("kill -KILL ")
    )


def _sandbox_command(command: str) -> list[str]:
    bwrap = os.environ.get("FOXAIR_FAKE_ADB_BWRAP", "/usr/bin/bwrap")
    if not Path(bwrap).is_file():
        raise FileNotFoundError(f"bubblewrap fehlt: {bwrap}")

    data = qemu_rootfs() / "data"
    cache = qemu_rootfs() / "cache"
    tmp = device_tmp()
    for path in (data, cache, tmp):
        if not path.is_dir():
            raise FileNotFoundError(f"ADB-Mountquelle fehlt: {path}")

    argv = [
        bwrap,
        "--bind", "/", "/",
        "--dev-bind", "/dev", "/dev",
        "--dir", "/data",
        "--dir", "/cache",
        "--bind", str(data), "/data",
        "--bind", str(cache), "/cache",
        "--bind", str(tmp), "/tmp",
        "--",
        "/bin/sh", "-c", command,
    ]

    # The production supervisor starts its runtime hook as a detached child.
    # The work-lab QEMU process deliberately lives in a private network
    # namespace, and its ARM remote-GDB listener is bound to 127.0.0.1 there.
    # Run only the autonomous supervisor in that same namespace so its
    # unmodified hook reaches the exact QEMU/GDB path used by the lab.  Other
    # fake-ADB commands retain the normal host namespace.
    if "dtu_ota_supervisor.sh" in command and " run " in command:
        pids = service_pids()
        nsenter = Path("/usr/bin/nsenter")
        if pids and nsenter.is_file():
            argv = [str(nsenter), "-t", str(pids[0]), "-n", "--", *argv]

    return argv


def _host_shell(command: str) -> tuple[int, bytes]:
    try:
        argv = _sandbox_command(command)
    except (FileNotFoundError, OSError) as exc:
        return 127, (str(exc) + "\n").encode()

    completed = subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=120,
        env={**os.environ, "TMPDIR": "/tmp"},
    )
    return completed.returncode, completed.stdout


_PROCESS_MEMORY_READ = re.compile(
    r"^dd\s+if=/proc/\d+/mem\s+bs=1\s+skip=(\d+)\s+count=(\d+)"
    r"\s+2>/dev/null\s*\|\s*od\s+-An\s+-v\s+-tx1$"
)


def _display_board_version(wire_version: str) -> str:
    """Convert the simulator's four-digit wire version to PHNIX display form."""
    if re.fullmatch(r"\d{4}", wire_version):
        return f"V{int(wire_version[-2])}.{int(wire_version[-1])}"
    return "V3.3"


def _simulated_process_memory(address: int, length: int) -> bytes | None:
    """Expose the useful original-process globals through the fake ADB path.

    qemu-user cannot expose the ARM virtual addresses via the host's
    /proc/PID/mem.  Statistics are nevertheless authoritative: phnixIot4G
    writes them to its original persistent file.  Only the board identity is
    synthesized from the selected virtual-mainboard version.
    """
    statistics = root_path("/data/phnixIot_device_statisic")
    try:
        statistics_bytes = statistics.read_bytes()[:128]
    except OSError:
        statistics_bytes = b""
    if len(statistics_bytes) < 128:
        statistics_bytes = statistics_bytes.ljust(128, b"\0")

    state = scenario_state()
    board_version = _display_board_version(str(state.get("board_version", "0033")))
    board_info = (
        b"82400644\0"
        + board_version.encode("ascii")[:5].ljust(5, b"\0")
        + b"82300314\0"
        + b"0000\0"
    )
    u16 = lambda value: int(value).to_bytes(2, "little")
    u32 = lambda value: int(value).to_bytes(4, "little")
    padded = lambda value, size: value.encode("ascii")[:size].ljust(size, b"\0")
    pclient = 0x120000
    hook = root_path("/tmp/phnix_ota_hook")
    runtime_file = _runtime_sim_home() / "runtime.json"
    try:
        runtime_state = json.loads(runtime_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        runtime_state = {}
    cloud_blocked = bool(runtime_state.get("cloud_blocked"))
    mqtt_init_signal = 0 if cloud_blocked else 1
    mqtt_state = 0 if cloud_blocked else 2
    segments = (
        (0x91B60, statistics_bytes),
        (0x93124, u32(0)),
        (0x935E1, board_info),
        (0x9365C, padded("89999000000000000001", 22)),
        (0x93674, padded("999990000000001", 17)),
        (0x93688, padded("000000000000001", 32)),
        (0x936A8, u32(mqtt_init_signal)),
        (0x94EB4, u32(pclient)),
        (0x97FE8, u32(1)),
        (0x97FEC, u32(1)),
        (0x98020, bytes([1])),
        (0x98022, u16(262)),
        (0x98024, u16(1)),
        (0x98026, padded("FoxAir LAB", 64)),
        (0x98168, u16(0x1234)),
        (0x9816C, u32(0x00F0A123)),
        (0x981B4, b"".join(u32(value) for value in (1, 1, 1, 0, 1, 8))),
        (0x98912, bytes([2])),
        (0x9896C, bytes(64)),
        (0x989B0, bytes(64)),
        (0x98A58, padded("FOXAir-TestVM", 64)),
        (0x98A98, padded("foxairLab", 24)),
        (0x98AB0, b"".join(u32(value) for value in (1, 3, 7))),
        (pclient + 0x4DC, u32(mqtt_state)),
    )
    for start, data in segments:
        offset = address - start
        if offset >= 0 and offset + length <= len(data):
            return data[offset:offset + length]
    return None


def _process_memory_shell(command: str) -> tuple[int, bytes] | None:
    match = _PROCESS_MEMORY_READ.fullmatch(command)
    if match is None:
        return None
    address, length = (int(value) for value in match.groups())
    data = _simulated_process_memory(address, length)
    if data is None:
        return 1, b""
    rendered = " ".join(f"{value:02x}" for value in data)
    return 0, f" {rendered}\n".encode("ascii")


def shell(command: str) -> tuple[int, bytes]:
    command = command.strip()

    process_memory = _process_memory_shell(command)
    if process_memory is not None:
        return process_memory

    # Read-only synthetic PDP interface matching the VM's QMI/LTE lab state.
    if command == "cat /proc/net/route":
        return 0, (
            b"Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
            b"rmnet_data0\t00000000\t0100FA0A\t0003\t0\t0\t0\t00000000\n"
        )
    if command in {
        "ip -o -4 addr show dev rmnet_data0 2>/dev/null",
        "ip -o -4 addr show 2>/dev/null",
    }:
        return 0, b"7: rmnet_data0    inet 10.250.0.2/24 scope global rmnet_data0\n"

    # The production helper is valid on the real ARM modem. In qemu-user mode
    # its gdbserver --attach would target the host QEMU process, so use the
    # deterministic updater-facing state machine instead.
    if command.startswith("/data/phnix_ota_runtime_hook "):
        return _runtime_helper_shell(command)

    if _phnix_special(command):
        return work.shell(command)

    if command == "mkdir -p /data/phnix_local_ota":
        # End the warmed idle run before the updater starts copying files.
        # Stopping it only together with the later httpd command leaves a
        # narrow race in which the newly started server can see the retiring
        # runner's mount state and answer the first verification request with
        # HTTP 404.
        work.stop_runner()

    if "busybox httpd -p 127.0.0.1:8081 -h /data/phnix_local_ota" in command:
        # The warmed Work-Lab owns a fixture HTTP server on the same loopback
        # port.  Staging belongs to the updater, so retire the idle runner
        # before starting the updater's server.  The real OTA helper starts a
        # fresh, complete QEMU run immediately afterwards.
        # Backward-compatible fallback for clients which do not create the
        # staging directory in a separate command.
        if work._read_runner_pid() is not None:
            work.stop_runner()

    if command == "netstat -lnt 2>/dev/null | awk '$4 ~ /:8081$/ {print}'":
        return 0, b""

    return _host_shell(command)


def main() -> int:
    return work.main()


if __name__ == "__main__":
    raise SystemExit(main())
