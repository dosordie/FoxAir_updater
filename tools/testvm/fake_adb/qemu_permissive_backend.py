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
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

HERE = Path(__file__).resolve().parent
WORK_BACKEND = HERE / "qemu_work_lab_backend.py"
RUNTIME_SIMULATOR = HERE / "phnix_ota_simulator.py"


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


def _runtime_helper_shell(command: str) -> tuple[int, bytes]:
    _runtime_sim_prepare()
    hook = root_path("/tmp/phnix_ota_hook")
    hook.mkdir(parents=True, exist_ok=True)
    action = command.split()[1] if len(command.split()) > 1 else ""
    if action in {"run", "same-version-probe", "handshake-probe", "cancel", "cancel-probe"}:
        (hook / "run.active").touch()
    code, output = runtime_sim.shell(command)
    if action in {"stop", "restore-original"}:
        _cleanup_runtime_markers()
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
        or (command.startswith("netstat -nt") and ":1883" in command)
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

    return [
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


def shell(command: str) -> tuple[int, bytes]:
    command = command.strip()

    # The production helper is valid on the real ARM modem. In qemu-user mode
    # its gdbserver --attach would target the host QEMU process, so use the
    # deterministic updater-facing state machine instead.
    if command.startswith("/data/phnix_ota_runtime_hook "):
        return _runtime_helper_shell(command)

    if _phnix_special(command):
        return work.shell(command)

    if command == "netstat -lnt 2>/dev/null | awk '$4 ~ /:8081$/ {print}'":
        return 0, b""

    return _host_shell(command)


def main() -> int:
    return work.main()


if __name__ == "__main__":
    raise SystemExit(main())
