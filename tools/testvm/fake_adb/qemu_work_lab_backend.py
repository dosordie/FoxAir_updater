#!/usr/bin/env python3
"""Runtime backend for the Work-created PHNIX QEMU lab.

This module wraps ``qemu_lab_adapter.py``. The original adapter owns the stable
rootfs mapping and process inspection. This layer adapts two facts confirmed on
the real Debian VM:

* the imported ARM rootfs intentionally has no /bin/sh or BusyBox; ADB shell
  therefore has to be represented on the Debian host while /data, /cache and
  /tmp continue to map into the QEMU rootfs;
* phnixIot4G is not a permanently running daemon in the lab. It is started by
  tools/run_scenario_lab.sh for a bounded scenario run together with PTYs,
  AT/QMI stubs and rs485_fault_emulator.py.

Only updater-facing shell commands are emulated here. No command is ever
executed by blindly substituting absolute paths into a host shell.
"""

from __future__ import annotations

import argparse
import shutil
import importlib.util
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import ModuleType

HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / "qemu_lab_adapter.py"
MAX_RUN_SECONDS = 3600
_IDLE_RESTART_LOCK = threading.Lock()
_INTENTIONAL_RUNNER_STOP = threading.Event()
_SERVICE_WATCHDOG_LOCK = threading.Lock()
_SERVICE_WATCHDOG_THREAD: threading.Thread | None = None
DEFAULT_RUN_SECONDS = int(os.environ.get("FOXAIR_QEMU_RUN_SECONDS", str(MAX_RUN_SECONDS)))
INTENTIONAL_STOP_TTL_SECONDS = 240


def _load_base() -> ModuleType:
    spec = importlib.util.spec_from_file_location("foxair_qemu_lab_base", BASE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"QEMU base adapter nicht ladbar: {BASE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


base = _load_base()

# Interface consumed by foxair_fake_adb_server.py
sim_home = base.sim_home
root_path = base.root_path
reset_state = base.reset_state
service_pids = base.service_pids
qemu_rootfs = base.qemu_rootfs
lab_root = base.lab_root
scenario_state = base.scenario_state
_original_ota_json: str | None = None


def set_original_ota_json(payload: str) -> None:
    global _original_ota_json
    encoded = payload.encode("ascii")
    if len(encoded) >= 232:
        raise ValueError(f"OTA JSON exceeds original 232-byte buffer: {len(encoded)}")
    _original_ota_json = payload


def _runtime_dir() -> Path:
    path = base.state_root() / "qemu-adb"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pid_file() -> Path:
    return _runtime_dir() / "scenario-lab.pid"


def _runner_log() -> Path:
    return _runtime_dir() / "scenario-lab.out"


def _intentional_stop_marker() -> Path:
    return _runtime_dir() / "intentional-runner-stop"


def _intentional_stop_active() -> bool:
    if _INTENTIONAL_RUNNER_STOP.is_set():
        return True
    marker = _intentional_stop_marker()
    try:
        expires_at = float(marker.read_text().strip())
    except (OSError, ValueError):
        marker.unlink(missing_ok=True)
        return False
    if expires_at > time.time():
        return True
    marker.unlink(missing_ok=True)
    return False


def _begin_intentional_stop() -> bool:
    already_active = _intentional_stop_active()
    _INTENTIONAL_RUNNER_STOP.set()
    marker = _intentional_stop_marker()
    marker.write_text(f"{time.time() + INTENTIONAL_STOP_TTL_SECONDS:.3f}\n", encoding="ascii")
    return already_active


def _end_intentional_stop(already_active: bool) -> None:
    _INTENTIONAL_RUNNER_STOP.clear()
    if not already_active:
        _intentional_stop_marker().unlink(missing_ok=True)


def _runner_meta() -> Path:
    return _runtime_dir() / "scenario-lab.json"


def _override_late_gdb(source_name: str) -> None:
    source = HERE / source_name
    target = lab_root() / "tools/gdb_local_ota_handler_late.gdb"
    backup = target.with_suffix(target.suffix + ".foxair-original")
    if target.exists() and not backup.exists():
        shutil.copy2(target, backup)
    if source_name == "gdb_original_ota_1fe40.gdb" and _original_ota_json is not None:
        script = source.read_text(encoding="utf-8")
        escaped = _original_ota_json.replace("\\", "\\\\").replace('"', '\\"')
        script = re.sub(
            r'^set \{char\[232\]\} 0x94ab4 = ".*"$',
            f'set {{char[232]}} 0x94ab4 = "{escaped}"',
            script,
            flags=re.MULTILINE,
        ).replace("FOXAIR_OTA_INJECT_0033", "FOXAIR_OTA_INJECT")
        target.write_text(script, encoding="utf-8")
    else:
        shutil.copy2(source, target)


def _restore_late_gdb() -> None:
    target = lab_root() / "tools/gdb_local_ota_handler_late.gdb"
    backup = target.with_suffix(target.suffix + ".foxair-original")
    if backup.exists():
        shutil.copy2(backup, target)


def _ensure_rootfs_busybox() -> tuple[bool, str]:
    """Restore the ARM shell applets present in the imported modem runtime."""
    source = lab_root() / "runtime-import/source/SIM7600_Runtime/bin/busybox"
    if not source.is_file():
        return False, f"ARM-BusyBox des Runtime-Imports fehlt: {source}"
    bin_dir = qemu_rootfs() / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / "busybox"
    if not target.is_file() or target.stat().st_size != source.stat().st_size:
        shutil.copy2(source, target)
    target.chmod(0o755)
    for applet in ("sh", "rm", "cp", "mv", "mkdir", "chmod", "sync", "md5sum"):
        link = bin_dir / applet
        if link.exists() and not link.is_symlink():
            continue
        link.unlink(missing_ok=True)
        link.symlink_to("busybox")
    return True, "ARM-BusyBox-Applets im QEMU-RootFS vorhanden"


def _remove_rootfs_busybox_overlay() -> None:
    """Remove only applets created by _ensure_rootfs_busybox."""
    bin_dir = qemu_rootfs() / "bin"
    for applet in ("sh", "rm", "cp", "mv", "mkdir", "chmod", "sync", "md5sum"):
        link = bin_dir / applet
        if link.is_symlink() and os.readlink(link) == "busybox":
            link.unlink(missing_ok=True)
    target = bin_dir / "busybox"
    source = lab_root() / "runtime-import/source/SIM7600_Runtime/bin/busybox"
    if target.is_file() and source.is_file() and target.stat().st_size == source.stat().st_size:
        target.unlink(missing_ok=True)
    try:
        bin_dir.rmdir()
    except OSError:
        pass


def _read_runner_pid() -> int | None:
    try:
        pid = int(_pid_file().read_text().strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        _pid_file().unlink(missing_ok=True)
        return None
    return pid


def _process_is_running(pid: int) -> bool:
    """Treat a terminated but not yet reaped child as stopped."""
    try:
        fields = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
    except (OSError, IndexError):
        return False
    return bool(fields) and fields[0] != "Z"


def _remove_stale_lab_device_links() -> None:
    """Remove only PTY links owned by a previous Work-Lab invocation."""
    dev = qemu_rootfs() / "dev"
    for name in ("ttyGS0", "smd8", "ttyHSL2"):
        path = dev / name
        if path.is_symlink():
            path.unlink(missing_ok=True)


def _lab_process_groups() -> set[int]:
    """Return process groups belonging to the current Work-Lab invocation."""
    own_group = os.getpgrp()
    groups: set[int] = set()
    markers = (
        "phnixIot4G", "run_scenario_lab.sh", "gdb-multiarch", "socat",
        "rs485_fault_emulator.py", "mqtt_scenario_stub.py", "qmux_stub.py",
        "at_emulator.py", "credential_http_stub.py", "firmware_http_stub.py",
    )
    lab_marker = str(lab_root())
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            group = os.getpgid(int(entry.name))
        except (OSError, ValueError, ProcessLookupError):
            continue
        if group != own_group and lab_marker in raw and any(marker in raw for marker in markers):
            groups.add(group)
    return groups


def _stop_runner_impl() -> None:
    pid = _read_runner_pid()
    if pid is not None:
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            pass
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if not _process_is_running(pid):
                break
            time.sleep(0.1)
        else:
            try:
                os.killpg(pid, signal.SIGKILL)
            except OSError:
                pass
    _pid_file().unlink(missing_ok=True)
    # run_scenario_lab creates separate process groups inside unshare. Killing
    # only its outer shell can otherwise leave old ARM/GDB instances behind,
    # making the next scenario race against several "modems".
    groups = _lab_process_groups()
    for group in groups:
        try:
            os.killpg(group, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and _lab_process_groups():
        time.sleep(0.1)
    for group in _lab_process_groups():
        try:
            os.killpg(group, signal.SIGKILL)
        except OSError:
            pass
    time.sleep(0.2)
    # A host/VM reboot cannot run run_scenario_lab.sh's EXIT trap.  Its
    # simulator-owned PTY symlinks then survive and make every later scenario
    # fail with "already exists".  Real files/device nodes remain fail-closed.
    _remove_stale_lab_device_links()
    _restore_late_gdb()
    _remove_rootfs_busybox_overlay()


def _stop_runner() -> None:
    """Stop the complete lab deliberately without triggering its modem watchdog."""
    already_suppressed = _begin_intentional_stop()
    try:
        _stop_runner_impl()
    finally:
        _end_intentional_stop(already_suppressed)


def _scenario_to_lab_env(kind: str, value: str) -> tuple[dict[str, str], str] | None:
    """Translate public test names to run_scenario_lab.sh's real knobs.

    Only mappings directly supported by the observed rs485_fault_emulator CLI
    are accepted. Unsupported historical Python-simulator names fail instead
    of being silently approximated.
    """
    env = {
        "RS485_STUB": "1",
        # The original service does not reach its normal cyclic loop without
        # the LTE/QMI initialization replies used in the proven Work run.
        "QMUX_STUB": "1",
        "QMUX_INIT_PROFILE": "1",
        "QMUX_CLIENT_ID": "1",
        # Normal modem operation already has credentials and an established
        # cloud connection. Keep both local/offline stubs active outside OTA
        # as well, otherwise phnixIot4G repeats credential HTTP registration.
        "CREDENTIAL_STUB": "1",
        "MQTT_TLS_STUB": "1",
        # This makes rs485_fault_emulator validate/ACK actual C5A8 traffic but
        # does not inject an OTA command itself. The Windows updater remains the
        # actor that stages/injects the OTA request.
        "LOCAL_OTA_FULL_TRANSFER": "1",
        "FAULT_SCENARIO": "success",
        # The board peer compares this value with the version offered in C350.
        # It must not infer the offered version from the historical V3.3 fixture.
        "BOARD_VERSION": scenario_state().get("board_version", "0033"),
    }
    label = f"foxair-adb-{kind}-{value}"

    if kind == "scenario":
        faults = {
            "success": "success",
            "success-real-timing": "success",
            "restart-at-50-resume": "success",
            "same-version": "c350-status0",
            "stall-c350": "no-c350-status",
            "stall-c5a8": "no-block-ack",
        }
        fault = faults.get(value)
        if fault is None:
            return None
        env["FAULT_SCENARIO"] = fault
        if value == "success-real-timing":
            env["OTA_TIMING_PROFILE"] = "real-v34"
        if value == "restart-at-50-resume":
            env["BOARD_RESUME_STATE"] = str(
                lab_root() / "rootfs/data/foxair_board_ota_resume.json"
            )
        return env, label

    if kind == "handshake-scenario":
        faults = {
            "success": "success",
            "missing-status-2": "no-c357-status",
        }
        fault = faults.get(value)
        if fault is None:
            return None
        env["FAULT_SCENARIO"] = fault
        return env, label

    if kind == "same-version-scenario":
        faults = {
            "success": "c350-status0",
            "status-1": "success",
        }
        fault = faults.get(value)
        if fault is None:
            return None
        env["FAULT_SCENARIO"] = fault
        return env, label

    if kind == "cancel-scenario":
        if value == "success":
            env["CANCEL_ACK"] = "1"
        elif value == "no-response":
            env["CANCEL_ACK"] = "0"
        else:
            return None
        return env, label

    return None


def _start_runner_impl(
    kind: str, value: str, *, original_ota: bool = False,
    resume_boot: bool = False,
) -> tuple[bool, str]:
    translated = _scenario_to_lab_env(kind, value)
    if translated is None:
        return (
            False,
            f"{kind}={value} ist im vorhandenen Work-Lab nicht direkt abbildbar. "
            "Der RS485-Emulator unterstützt aktuell nur success, c350-status0, "
            "no-c350-status, no-c357-status, no-block-ack, wrong-block-ack, "
            "wrong-ssid-ack und drop-first-block-ack.",
        )
    extra_env, label = translated
    if original_ota:
        # Let the unmodified ARM phnixIot4G execute its observed OTA callback.
        # The existing Work-Lab GDB hook only supplies the cloud JSON which is
        # unavailable in the offline VM; all subsequent protocol work is done
        # by the original process and the real RS485 fault emulator.
        extra_env["LOCAL_OTA_HANDLER"] = "1"
        extra_env["LOCAL_OTA_HANDLER_LATE"] = "1"
        extra_env["LOCAL_OTA_FULL_TRANSFER"] = "1"
        # 0x1FE40 belongs to the real MQTT yield loop.  The isolated VM must
        # therefore provide the already available local TLS/MQTT endpoint;
        # otherwise the original service initializes RS485 but can never reach
        # the live-proven injection point.
        extra_env["MQTT_TLS_STUB"] = "1"
        extra_env["CREDENTIAL_STUB"] = "1"
        extra_env["DYNAMIC_LOCAL_OTA"] = "1"
        label = f"foxair-adb-original-ota-{value}"
    elif kind == "scenario" and not resume_boot:
        # DTU_runner owns the first and only GDB connection. qemu-user's
        # remote stub is not reliable after detach/re-attach, unlike gdbserver
        # on the physical DTU.
        extra_env["AUTONOMOUS_DTU_RUNNER"] = "1"
    runner = lab_root() / "tools/run_scenario_lab.sh"
    if not runner.is_file() or not os.access(runner, os.X_OK):
        return False, f"Work-Lab Runner fehlt oder ist nicht ausführbar: {runner}"
    _stop_runner()
    if original_ota:
        shell_ok, shell_message = _ensure_rootfs_busybox()
        if not shell_ok:
            return False, shell_message
    if kind == "scenario" and extra_env.get("AUTONOMOUS_DTU_RUNNER") != "1":
        _override_late_gdb(
            "gdb_original_ota_1fe40.gdb" if original_ota
            else "gdb_warm_detach.gdb"
        )
    env = os.environ.copy()
    env.update(extra_env)
    env["LAB_ROOT"] = str(lab_root())
    duration = max(5, min(DEFAULT_RUN_SECONDS, MAX_RUN_SECONDS))
    log_path = _runner_log()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # This is a current-run status log. Per-run forensic logs remain preserved
    # below LAB_ROOT/logs, while truncation prevents stale failures appearing
    # repeatedly in every later control-command error.
    log_handle = log_path.open("wb", buffering=0)
    try:
        proc = subprocess.Popen(
            [str(runner), str(duration), label],
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        log_handle.close()
    _pid_file().write_text(f"{proc.pid}\n")
    _runner_meta().write_text(
        json.dumps(
            {
                "kind": kind,
                "value": value,
                "pid": proc.pid,
                "duration_seconds": duration,
                "environment": extra_env,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "original_ota": original_ota,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    # run_scenario_lab.sh creates PTYs and then starts qemu. Do not return
    # success until the original ARM process is observable.
    # A cold ARM/QEMU start on the one-vCPU lab VM was observed to reach the
    # injected parser only just before the old 90-second limit.  Killing that
    # healthy run produced a second phnixIot4G PID group and a second
    # `set /dev/ttyGS0` line.  Keep the fail-safe retry, but allow the original
    # service enough time to emit the first C350 proof before declaring it
    # failed.
    ready_seconds = 150.0 if original_ota else 90.0
    deadline = time.monotonic() + ready_seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            tail = ""
            try:
                tail = log_path.read_text(errors="replace")[-4000:]
            except OSError:
                pass
            return False, f"run_scenario_lab.sh endete früh mit Exit {proc.returncode}:\n{tail}"
        current_service_pids = service_pids()
        if len(current_service_pids) == 1:
            candidates = list((lab_root() / "logs").glob(f"{label}-*"))
            if candidates:
                run_dir = max(candidates, key=lambda path: path.stat().st_mtime_ns)
                if extra_env.get("AUTONOMOUS_DTU_RUNNER") == "1":
                    meta = json.loads(_runner_meta().read_text(encoding="utf-8"))
                    meta["run_dir"] = str(run_dir)
                    _runner_meta().write_text(
                        json.dumps(meta, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    return True, (
                        f"Work-QEMU-Szenario {kind}={value} für autonomen DTU-Runner "
                        f"bereit (QEMU PID vorhanden, GDB-StUB frei)"
                    )
                gdb_log = run_dir / "gdb-local-ota-handler.log"
                rs485_log = run_dir / "ttyHSL2-transcript.txt"
                gdb_text = rs485_text = ""
                try:
                    gdb_text = gdb_log.read_text(errors="replace")
                    rs485_text = rs485_log.read_text(errors="replace")
                    detached = (
                        (
                            "FOXAIR_OTA_INJECT" in gdb_text
                            and "c350-minimal-confirm" in rs485_text
                        ) if original_ota
                        else "FOXAIR_WARM_DETACHED" in gdb_text
                    )
                    board_ready = "product-key-frame" in rs485_text
                except OSError:
                    detached = board_ready = False
                resume_ready = (
                    resume_boot
                    and "c544-software-info" in rs485_text
                    and "DTU -> BOARD 63 10 c5 a8" in rs485_text
                )
                if resume_ready:
                    meta = json.loads(_runner_meta().read_text(encoding="utf-8"))
                    meta["run_dir"] = str(run_dir)
                    meta["resume_boot"] = True
                    _runner_meta().write_text(
                        json.dumps(meta, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    return True, (
                        f"Work-QEMU-Szenario {kind}={value} nach persistentem "
                        "C544/C5A8-Resume wieder aktiv"
                    )
                if detached and board_ready:
                    meta = json.loads(_runner_meta().read_text(encoding="utf-8"))
                    meta["run_dir"] = str(run_dir)
                    _runner_meta().write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                    # Do not replace the sourced GDB command file while GDB is
                    # still consuming it.  With the original OTA script, the
                    # readiness markers occur before the C36E breakpoint and
                    # an in-place restore can splice the old file into the
                    # active command stream (observed as `Undefined command:
                    # "ent"`).  _stop_runner() restores the original file only
                    # after the complete GDB/QEMU session has ended.
                    return True, f"Work-QEMU-Szenario {kind}={value} vorgewärmt (runner PID {proc.pid})"
        time.sleep(0.1)
    return (
        False,
        f"Work-QEMU-Runner PID {proc.pid} läuft, aber das Szenario wurde nach {ready_seconds:.0f} s nicht bereit. "
        f"Log: {log_path}",
    )


def _start_runner(
    kind: str, value: str, *, original_ota: bool = False,
    resume_boot: bool = False,
) -> tuple[bool, str]:
    """Start one scenario while suppressing death detection for its replacement gap."""
    already_suppressed = _begin_intentional_stop()
    try:
        return _start_runner_impl(
            kind, value, original_ota=original_ota, resume_boot=resume_boot,
        )
    finally:
        _end_intentional_stop(already_suppressed)


def start_original_ota(value: str) -> tuple[bool, str, Path | None]:
    """Start a complete original-service run, retrying one pre-C350 race.

    A run is ready only after the board identity exchange and the GDB injection
    marker.  A QEMU/GDB disconnect before that point is safe to retry because
    no C350 offer has reached the simulated board yet.
    """
    errors: list[str] = []
    for attempt in (1, 2):
        ok, message = _start_runner("scenario", value, original_ota=True)
        if ok:
            try:
                meta = json.loads(_runner_meta().read_text(encoding="utf-8"))
                run_dir = Path(meta["run_dir"])
            except (OSError, KeyError, ValueError, json.JSONDecodeError):
                ok = False
                message = "Original-OTA-Run-Verzeichnis wurde nicht angelegt"
            else:
                meta["startup_attempt"] = attempt
                meta["ota_gdb_offset"] = 0
                meta["ota_transcript_offset"] = 0
                _runner_meta().write_text(
                    json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                retry_note = "" if attempt == 1 else " (automatischer zweiter Start)"
                return True, message + retry_note, run_dir
        errors.append(f"Versuch {attempt}: {message}")
        _stop_runner()
    return False, "Original-OTA-Start fehlgeschlagen; " + " | ".join(errors), None


def stop_runner() -> None:
    _stop_runner()


def _ota_restart_blocked() -> bool:
    hook = base.root_path("/tmp/phnix_ota_hook")
    return any(
        (hook / marker).exists()
        for marker in ("run.active", "transfer-started", "original-service-owns")
    )


def _restart_context() -> tuple[str, str]:
    """Return the currently selected lab path without changing persistent state."""
    try:
        meta = json.loads(_runner_meta().read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        meta = {}
    kind = str(meta.get("kind", "scenario"))
    value = str(meta.get("value", scenario_state().get("scenario", "success")))
    if _scenario_to_lab_env(kind, value) is None:
        return "scenario", str(scenario_state().get("scenario", "success"))
    return kind, value


def _schedule_idle_service_restart(dead_pids: tuple[int, ...] = ()) -> bool:
    """Emulate the host-side modem supervisor after an external QEMU death.

    This is simulator infrastructure.  It deliberately restarts the same lab
    scenario without calling reset_ota_runtime(), so RS485 selection, MQTT
    selection, OTA_INFO and a persisted board-resume record survive.
    """
    if not _IDLE_RESTART_LOCK.acquire(blocking=False):
        return True

    kind, value = _restart_context()

    def restart() -> None:
        try:
            ok, message = _start_runner(kind, value)
            new_pids: tuple[int, ...] = ()
            if ok:
                stable = 0
                deadline = time.monotonic() + 10.0
                while time.monotonic() < deadline:
                    current = tuple(service_pids())
                    if len(current) == 1 and current != dead_pids:
                        stable += 1
                        new_pids = current
                        if stable >= 3:
                            break
                    else:
                        stable = 0
                        new_pids = ()
                    time.sleep(0.2)
                if not new_pids or stable < 3:
                    ok = False
                    message = (
                        "QEMU service restart did not produce exactly one stable "
                        "new phnixIot4G PID"
                    )
            status = {
                "ok": ok,
                "message": message,
                "kind": kind,
                "value": value,
                "dead_pids": list(dead_pids),
                "new_pids": list(new_pids),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            path = base.state_root() / "qemu-adb" / "service-restart-status.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        finally:
            _IDLE_RESTART_LOCK.release()

    threading.Thread(
        target=restart,
        name="foxair-phnix-supervisor-restart",
        daemon=True,
    ).start()
    return True


def _service_watchdog_loop() -> None:
    """Watch the real host QEMU PID, including TERM issued inside bwrap.

    The autonomous DTU supervisor executes ``kill -TERM`` itself, so that kill
    never passes through fake-ADB's shell dispatcher.  Watching the actual
    qemu-arm process models the physical modem supervisor at the correct layer.
    """
    observed: tuple[int, ...] = ()
    while True:
        try:
            observed = _service_watchdog_transition(observed, tuple(service_pids()))
        except Exception as exc:  # keep simulator supervision alive for diagnostics
            path = _runtime_dir() / "service-watchdog-error.log"
            try:
                path.write_text(f"{time.time():.6f} {exc!r}\n", encoding="utf-8")
            except OSError:
                pass
        time.sleep(0.5)


def _service_watchdog_transition(
    observed: tuple[int, ...], current: tuple[int, ...],
) -> tuple[int, ...]:
    """Apply one deterministic watchdog sample; split out for unit tests."""
    if len(current) == 1:
        return current
    if not current and observed:
        if not _intentional_stop_active():
            _schedule_idle_service_restart(observed)
        return ()
    return observed


def ensure_service_watchdog() -> None:
    """Start exactly one watchdog in the long-lived fake-ADB server process."""
    global _SERVICE_WATCHDOG_THREAD
    with _SERVICE_WATCHDOG_LOCK:
        if _SERVICE_WATCHDOG_THREAD is not None and _SERVICE_WATCHDOG_THREAD.is_alive():
            return
        _SERVICE_WATCHDOG_THREAD = threading.Thread(
            target=_service_watchdog_loop,
            name="foxair-qemu-service-watchdog",
            daemon=True,
        )
        _SERVICE_WATCHDOG_THREAD.start()


def inject_mqtt(kind: str, payload_hex: str | None = None) -> tuple[bool, str]:
    """Queue one cloud-to-device MQTT message in the active isolated lab."""
    if kind == "status-request":
        topic = "/a1LABTEST01/LABDEVICE001/user/get"
        payload = DEVICE_STATUS_REQUEST_HEX
        label = "mainboard-status-request-07d1"
    elif kind == "raw":
        topic = "/a1LABTEST01/LABDEVICE001/user/get"
        payload = (payload_hex or "").replace(" ", "")
        if (not payload or len(payload) > 8192
                or re.fullmatch(r"[0-9a-fA-F]+", payload) is None or len(payload) % 2):
            return False, "mqtt-send raw erwartet eine gerade Anzahl Hex-Zeichen"
        label = "raw-user-get"
    else:
        return False, f"Unbekannte MQTT-Nachricht: {kind}"
    try:
        meta = json.loads(_runner_meta().read_text(encoding="utf-8"))
        run_dir = Path(meta["run_dir"])
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        return False, "Kein vorbereiteter Work-QEMU-Run aktiv"
    control = run_dir / "mqtt-control.sock"
    if not control.is_socket():
        return False, f"MQTT-Steuerkanal ist nicht aktiv: {control}"
    request = json.dumps({"topic": topic, "payload_hex": payload, "label": label}) + "\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3.0)
            client.connect(str(control))
            client.sendall(request.encode("utf-8"))
            reply = client.recv(4096).decode("utf-8", errors="replace").strip()
    except OSError as exc:
        return False, f"MQTT-Nachricht konnte nicht eingereiht werden: {exc}"
    return True, reply or f"MQTT-Nachricht {label} eingereiht"


DEVICE_STATUS_REQUEST_HEX = "630307d1005a9cfe"


def _idle_ota_info() -> bytes:
    data = bytearray(220)
    data[28:34] = b"V1.0\0\0"
    crc = 0xFFFF
    for value in data[4:]:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    data[:4] = ((~crc) & 0xFFFF).to_bytes(4, "little")
    return bytes(data)


def reset_ota_runtime() -> None:
    """Return only updater-owned VM state to an idle modem baseline."""
    root_path("/data/phnixIot_device_OTA_INFO").write_bytes(_idle_ota_info())
    for remote in (
        "/data/phnix_ota_runtime_hook", "/data/phnix_local_ota_stage.json",
        "/data/foxair_board_ota_resume.json",
        "/tmp/phnix_ota_status.json", "/tmp/phnix_handshake_trace.json",
    ):
        root_path(remote).unlink(missing_ok=True)
    for remote in ("/data/phnix_local_ota", "/tmp/phnix_ota_hook"):
        path = root_path(remote)
        if path.is_dir():
            shutil.rmtree(path)
    runtime_state = base.state_root() / "runtime-sim" / "runtime.json"
    runtime_state.parent.mkdir(parents=True, exist_ok=True)
    runtime_state.write_text(json.dumps({
        "running": False, "httpd": False, "held": False,
        "cloud_blocked": False, "watchdogs_paused": False,
        "recovery_running": False,
    }, separators=(",", ":")), encoding="utf-8")
    # The autonomous supervisor is executed in the fake-ADB /tmp namespace,
    # not ROOTFS/tmp. Remove its markers as part of an explicit VM reset.
    device_tmp = Path(os.environ.get(
        "FOXAIR_FAKE_ADB_TMP", str(base.state_root() / "device-tmp")
    ))
    for name in (
        "phnix_ota_hook", "phnix_ota_status.json", "phnix_ota_httpd.pid",
        "phnix_handshake_trace.json",
    ):
        path = device_tmp / name
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


def reset_autonomous_runner_state() -> None:
    """Forget all autonomous OTA runs only for an explicit VM lab reset."""
    runner_root = root_path("/data/foxair_ota_runner")
    if runner_root.is_dir():
        shutil.rmtree(runner_root)
    else:
        runner_root.unlink(missing_ok=True)


def _resume_restart_ready(kind: str, value: str, state: dict[str, str]) -> bool:
    """Recognise the second, state-preserving half of restart-at-50.

    Selecting the scenario initially must still create an idle baseline.  Once
    the board peer has persisted a confirmed block and OTA_INFO records an
    active image, selecting the same scenario means "restart the LTE/QEMU
    process now" and must not erase either side of the resume contract.
    """
    if kind != "scenario" or value != "restart-at-50-resume":
        return False
    if state.get("scenario") != value:
        return False
    resume = root_path("/data/foxair_board_ota_resume.json")
    info = root_path("/data/phnixIot_device_OTA_INFO")
    try:
        raw = info.read_bytes()
        offset = int.from_bytes(raw[212:216], "little")
        length = int.from_bytes(raw[216:220], "little")
    except OSError:
        return False
    return resume.is_file() and len(raw) == 220 and 0 < offset < length


def apply_control(kind: str, value: str) -> tuple[bool, str]:
    key_for_kind = {
        "board-version": "board_version",
        "scenario": "scenario",
        "cancel-scenario": "cancel_scenario",
        "handshake-scenario": "handshake_scenario",
        "same-version-scenario": "same_version_scenario",
    }
    if kind not in key_for_kind:
        return False, f"Unbekannte Scenario-Art: {kind}"

    # Re-use the base adapter's validation sets/state format without using its
    # old hook/socket discovery path.
    if kind == "board-version":
        if re.fullmatch(r"\d{4}", value) is None:
            return False, "board-version muss genau vier Ziffern enthalten"
    else:
        allowed = {
            "scenario": base.MAIN_SCENARIOS,
            "cancel-scenario": base.CANCEL_SCENARIOS,
            "handshake-scenario": base.HANDSHAKE_SCENARIOS,
            "same-version-scenario": base.SAME_VERSION_SCENARIOS,
        }[kind]
        if value not in allowed:
            return False, f"Unbekanntes {kind}: {value}"

    state = scenario_state()
    preserve_resume = _resume_restart_ready(kind, value, state)
    state[key_for_kind[kind]] = value
    base._write_scenario_state(state)
    if kind in {"scenario", "board-version"}:
        # Stop the old ARM process before clearing OTA_INFO. Otherwise it can
        # emit one stale C5A8 block into the newly reset board peer.
        _stop_runner()
        if not preserve_resume:
            reset_ota_runtime()
    scenario = state.get("scenario", "success")
    return _start_runner("scenario", scenario, resume_boot=preserve_resume)


def _df(remote: str) -> tuple[int, bytes]:
    path = root_path(remote)
    completed = subprocess.run(
        ["df", "-k", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode, completed.stdout


def _host_listener(port: int) -> bytes:
    for command in (["ss", "-lnt"], ["netstat", "-lnt"]):
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        lines = []
        marker = f":{port}"
        for line in completed.stdout.decode(errors="replace").splitlines():
            if marker in line:
                lines.append(line)
        if lines:
            return ("\n".join(lines) + "\n").encode()
    return b""


def _test_remote(kind: str, remote: str) -> bool:
    """Implement Android-style test predicates against the emulated rootfs."""
    path = root_path(remote)
    if kind == "e":
        return path.exists()
    if kind == "f":
        return path.is_file()
    if kind == "x":
        return path.is_file() and os.access(path, os.X_OK)
    return False


def shell(command: str) -> tuple[int, bytes]:
    command = command.strip()

    # Commands already implemented safely by the base adapter: process identity,
    # hashes, cat, watchdog/MQTT representation and signalling.
    if command == "pidof gdbserver gdb || true":
        # The persistent host-side debugger is simulator infrastructure, not a
        # debugger installed on the represented LTE modem.
        return 0, b""
    if command in {"pidof phnixIot4G || true", "pidof phnixIot4G"}:
        return base.shell(command)
    if command.startswith("p=$(pidof phnixIot4G"):
        return base.shell(command)
    if command.startswith("ps | awk") and "{helloworld}" in command:
        return base.shell(command)
    if re.match(r"netstat -(?:nt|tn)\b", command) and ":1883" in command:
        return base.shell(command)
    restart_match = re.fullmatch(r"kill -TERM\s+([0-9]+)", command)
    if restart_match and not _ota_restart_blocked():
        pid = int(restart_match.group(1))
        if pid not in service_pids():
            return 1, b"refusing to restart non-phnix QEMU pid\n"
        _schedule_idle_service_restart((pid,))
        return 0, b""
    if command.startswith("kill ") or (command.startswith("killall") and "phnixIot4G" in command):
        return base.shell(command)
    if re.fullmatch(r"cat ['\"]?/\S+['\"]?", command):
        return base.shell(command)
    if ("sha256sum" in command or "md5sum" in command) and "awk" in command:
        return base.shell(command)

    match = re.fullmatch(r"df -k (?P<path>/(?:data|cache))(?: 2>/dev/null)?", command)
    if match:
        return _df(match.group("path"))

    if command == "netstat -lnt 2>/dev/null | awk '$4 ~ /:8081$/ {print}'":
        return 0, _host_listener(8081)

    if "iptables -S OUTPUT" in command or "iptables -S INPUT" in command:
        # The Work lab deliberately runs inside an isolated network namespace and
        # does not need production MQTT guard rules on the Debian host.
        return 0, b""

    # Android/preflight predicates.  The controller intentionally asks whether
    # debugger/helper tools exist with forms such as:
    #   test -x /usr/bin/gdb; echo $?
    # The imported Work rootfs has no shell and no gdb, so this must be answered
    # from the mapped rootfs rather than attempted through ARM /bin/sh.
    match = re.fullmatch(r"test -(?P<kind>[efx]) ['\"]?(?P<path>/[^;'\"]+)['\"]?; echo \$\?", command)
    if match:
        result = _test_remote(match.group("kind"), match.group("path"))
        return 0, b"0\n" if result else b"1\n"

    match = re.fullmatch(r"chmod [0-7]+ ['\"]?(?P<path>/\S+?)['\"]?", command)
    if match:
        path = root_path(match.group("path"))
        if not path.exists():
            return 1, b""
        mode = int(command.split()[1], 8)
        path.chmod(mode)
        return 0, b""

    if command == "sync":
        try:
            os.sync()
        except AttributeError:
            pass
        return 0, b""

    return 127, (
        "ADB-Lab-Shell-Befehl noch nicht abgebildet: " + command + "\n"
    ).encode("utf-8")


def service_info() -> dict:
    info = base.service_info()
    info["backend"] = "work-qemu-lab"
    info["rootfs_has_shell"] = (qemu_rootfs() / "bin/sh").exists()
    info["scenario_runner_pid"] = _read_runner_pid()
    info["scenario_runner_log"] = str(_runner_log())
    try:
        info["scenario_runner"] = json.loads(_runner_meta().read_text())
    except (OSError, json.JSONDecodeError):
        info["scenario_runner"] = None
    info["scenario_control"] = "tools/run_scenario_lab.sh + rs485_fault_emulator.py"
    return info


def _print_status() -> None:
    print(json.dumps(service_info(), indent=2, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="FoxAir Work-QEMU fake-ADB backend")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("online")
    sub.add_parser("offline")
    sub.add_parser("runner-stop")
    mqtt = sub.add_parser("mqtt-send")
    mqtt.add_argument("kind", choices=("status-request", "raw"))
    mqtt.add_argument("payload_hex", nargs="?")
    reset = sub.add_parser("reset")
    reset.add_argument("scenario", nargs="?", default="success")
    for name in (
        "scenario", "board-version", "cancel-scenario",
        "handshake-scenario", "same-version-scenario",
    ):
        item = sub.add_parser(name)
        item.add_argument("value")
    args = parser.parse_args()

    try:
        if args.command == "status":
            _print_status()
            return 0
        if args.command == "online":
            marker = sim_home() / "started"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
            return 0
        if args.command == "offline":
            (sim_home() / "started").unlink(missing_ok=True)
            return 0
        if args.command == "runner-stop":
            _stop_runner()
            return 0
        if args.command == "mqtt-send":
            ok, message = inject_mqtt(args.kind, args.payload_hex)
            print(message)
            return 0 if ok else 3
        if args.command == "reset":
            _stop_runner()
            reset_state(args.scenario, "success")
            reset_ota_runtime()
            reset_autonomous_runner_state()
            ok, message = apply_control("scenario", args.scenario)
        else:
            ok, message = apply_control(args.command, args.value)
        print(message)
        return 0 if ok else 3
    except Exception as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
