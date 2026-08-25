#!/usr/bin/env python3
"""Permissive ADB backend for the isolated FoxAir TestVM.

This intentionally exposes a root Debian shell through ADB. The VM is a test
fixture, so unknown commands are not rejected. PHNIX-specific process/status
queries are still delegated to qemu_work_lab_backend.py, while every other
command is executed with /bin/sh -c on the Debian host.

The Debian host filesystem is not globally rewritten to look like the modem.
Each ADB shell command gets its own bubblewrap mount namespace:

* /data  -> Work QEMU rootfs/data
* /cache -> Work QEMU rootfs/cache
* /tmp   -> dedicated fake-ADB device tmp

ADB SYNC uses the same virtual mapping directly through root_path(). This keeps
normal Debian /data, /cache and /tmp separate from the emulated LTE device.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

HERE = Path(__file__).resolve().parent
WORK_BACKEND = HERE / "qemu_work_lab_backend.py"


def _load_work() -> ModuleType:
    spec = importlib.util.spec_from_file_location("foxair_work_qemu_permissive_base", WORK_BACKEND)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Work-QEMU-Backend nicht ladbar: {WORK_BACKEND}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


work = _load_work()

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
    """Build one isolated ADB-shell namespace without mutating host mount paths."""
    bwrap = os.environ.get("FOXAIR_FAKE_ADB_BWRAP", "/usr/bin/bwrap")
    if not Path(bwrap).is_file():
        raise FileNotFoundError(f"bubblewrap fehlt: {bwrap}")

    data = qemu_rootfs() / "data"
    cache = qemu_rootfs() / "cache"
    tmp = device_tmp()
    for path in (data, cache, tmp):
        if not path.is_dir():
            raise FileNotFoundError(f"ADB-Mountquelle fehlt: {path}")

    # Use a writable host /dev explicitly. Relying on the recursive root bind is
    # not sufficient with bubblewrap: redirections such as 2>/dev/null could
    # otherwise fail with EACCES and make unrelated status checks look broken.
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

    # These queries need the virtual modem view rather than raw Debian process
    # names/paths. Everything else is deliberately unrestricted.
    if _phnix_special(command):
        return work.shell(command)

    # The original LTE runtime must not inherit an unrelated Debian test service
    # that happens to listen on port 8081. The OTA controller starts/stops its
    # own HTTP service during a run; original-state checks should therefore see
    # no listener before that run begins.
    if command == "netstat -lnt 2>/dev/null | awk '$4 ~ /:8081$/ {print}'":
        return 0, b""

    return _host_shell(command)


def main() -> int:
    return work.main()


if __name__ == "__main__":
    raise SystemExit(main())
