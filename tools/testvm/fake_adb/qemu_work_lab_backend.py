#!/usr/bin/env python3
"""Runtime backend for the Work-created PHNIX QEMU lab.

This module wraps ``qemu_lab_adapter.py``.  The original adapter owns the stable
rootfs mapping and process inspection.  This layer adapts two facts confirmed on
the real Debian VM:

* the imported ARM rootfs intentionally has no /bin/sh or BusyBox; ADB shell
  therefore has to be represented on the Debian host while /data, /cache and
  /tmp continue to map into the QEMU rootfs;
* phnixIot4G is not a permanently running daemon in the lab.  It is started by
  tools/run_scenario_lab.sh for a bounded scenario run together with PTYs,
  AT/QMI stubs and rs485_fault_emulator.py.

Only updater-facing shell commands are emulated here.  No command is ever
executed by blindly substituting absolute paths into a host shell.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / "qemu_lab_adapter.py"
DEFAULT_RUN_SECONDS = int(os.environ.get("FOXAIR_QEMU_RUN_SECONDS", "1200"))


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


def _runtime_dir() -> Path:
    path = base.state_root() / "qemu-adb"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pid_file() -> Path:
    return _runtime_dir() / "scenario-lab.pid"


def _runner_log() -> Path:
    return _runtime_dir() / "scenario-lab.out"


def _runner_meta() -> Path:
    return _runtime_dir() / "scenario-lab.json"


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


def _stop_runner() -> None:
    pid = _read_runner_pid()
    if pid is None:
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        pass
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.1)
    else:
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass
    _pid_file().unlink(missing_ok=True)


def _scenario_to_lab_env(kind: str, value: str) -> tuple[dict[str, str], str] | None:
    """Translate public test names to run_scenario_lab.sh's real knobs.

    Only mappings directly supported by the observed rs485_fault_emulator CLI
    are accepted.  Unsupported historical Python-simulator names fail instead
    of being silently approximated.
    """
    env = {
        "RS485_STUB": "1",
        # This makes rs485_fault_emulator validate/ACK actual C5A8 traffic but
        # does not inject an OTA command itself.  The Windows updater remains the
        # actor that stages/injects the OTA request.
        "LOCAL_OTA_FULL_TRANSFER": "1",
        "FAULT_SCENARIO": "success",
    }
    label = f"foxair-adb-{kind}-{value}"

    if kind == "scenario":
        faults = {
            "success": "success",
            "same-version": "c350-status0",
            "stall-c350": "no-c350-status",
            "stall-c5a8": "no-block-ack",
        }
        fault = faults.get(value)
        if fault is None:
            return None
        env["FAULT_SCENARIO"] = fault
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


def _start_runner(kind: str, value: str) -> tuple[bool, str]:
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
    runner = lab_root() / "tools/run_scenario_lab.sh"
    if not runner.is_file() or not os.access(runner, os.X_OK):
        return False, f"Work-Lab Runner fehlt oder ist nicht ausführbar: {runner}"

    _stop_runner()
    env = os.environ.copy()
    env.update(extra_env)
    env["LAB_ROOT"] = str(lab_root())
    duration = max(5, min(DEFAULT_RUN_SECONDS, 1200))
    log_path = _runner_log()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("ab", buffering=0)
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
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # run_scenario_lab.sh creates PTYs and then starts qemu.  Do not return
    # success until the original ARM process is observable.
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            tail = ""
            try:
                tail = log_path.read_text(errors="replace")[-4000:]
            except OSError:
                pass
            return False, f"run_scenario_lab.sh endete früh mit Exit {proc.returncode}:\n{tail}"
        if service_pids():
            return True, f"Work-QEMU-Szenario {kind}={value} aktiv (runner PID {proc.pid})"
        time.sleep(0.1)
    return (
        False,
        f"Work-QEMU-Runner PID {proc.pid} läuft, aber phnixIot4G/QEMU wurde nach 8 s nicht erkannt. "
        f"Log: {log_path}",
    )


def apply_control(kind: str, value: str) -> tuple[bool, str]:
    key_for_kind = {
        "scenario": "scenario",
        "cancel-scenario": "cancel_scenario",
        "handshake-scenario": "handshake_scenario",
        "same-version-scenario": "same_version_scenario",
    }
    if kind not in key_for_kind:
        return False, f"Unbekannte Scenario-Art: {kind}"

    # Re-use the base adapter's validation sets/state format without using its
    # old hook/socket discovery path.
    allowed = {
        "scenario": base.MAIN_SCENARIOS,
        "cancel-scenario": base.CANCEL_SCENARIOS,
        "handshake-scenario": base.HANDSHAKE_SCENARIOS,
        "same-version-scenario": base.SAME_VERSION_SCENARIOS,
    }[kind]
    if value not in allowed:
        return False, f"Unbekanntes {kind}: {value}"

    state = scenario_state()
    state[key_for_kind[kind]] = value
    base._write_scenario_state(state)
    return _start_runner(kind, value)


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


def shell(command: str) -> tuple[int, bytes]:
    command = command.strip()

    # Commands already implemented safely by the base adapter: process identity,
    # hashes, cat, watchdog/MQTT representation and signalling.
    if command in {"pidof phnixIot4G || true", "pidof phnixIot4G", "pidof gdbserver gdb || true"}:
        return base.shell(command)
    if command.startswith("p=$(pidof phnixIot4G"):
        return base.shell(command)
    if command.startswith("ps | awk") and "{helloworld}" in command:
        return base.shell(command)
    if command.startswith("netstat -nt") and ":1883" in command:
        return base.shell(command)
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

    # File primitives that normally reach this module only when they were not
    # already handled by FakeAdbServer.generic_file_shell().
    match = re.fullmatch(r"test -([fe]) ['\"]?(?P<path>/[^;'\"]+)['\"]?; echo \$\?", command)
    if match:
        exists = root_path(match.group("path")).exists()
        return 0, b"0\n" if exists else b"1\n"

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
    reset = sub.add_parser("reset")
    reset.add_argument("scenario", nargs="?", default="success")
    for name in ("scenario", "cancel-scenario", "handshake-scenario", "same-version-scenario"):
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
        if args.command == "reset":
            reset_state(args.scenario, "success")
            ok, message = apply_control("scenario", args.scenario)
        else:
            ok, message = apply_control(args.command, args.value)
        print(message)
        return 0 if ok else 3
    except Exception as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
