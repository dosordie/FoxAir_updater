#!/usr/bin/env python3
"""Permissive ADB backend for the isolated FoxAir TestVM.

This intentionally exposes a root Debian shell through ADB.  The VM is a test
fixture, so unknown commands are not rejected.  PHNIX-specific process/status
queries are still delegated to qemu_work_lab_backend.py, while every other
command is executed with /bin/sh -c on the Debian host.

/data and /cache are expected to be symlinks created by install.sh that point
at the Work QEMU rootfs. /tmp intentionally uses the VM host /tmp so shell
scripts such as phnix_ota_runtime_hook and ADB file operations see the same
files.
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


def root_path(remote: str) -> Path:
    """Keep ADB SYNC consistent with the host shell namespace."""
    if not remote.startswith("/"):
        raise ValueError("Nur absolute Remote-Pfade werden unterstützt")
    if remote == "/tmp":
        return Path("/tmp")
    if remote.startswith("/tmp/"):
        return Path(remote)
    return work.root_path(remote)


def _phnix_special(command: str) -> bool:
    command = command.strip()
    return (
        command in {"pidof phnixIot4G || true", "pidof phnixIot4G"}
        or command.startswith("p=$(pidof phnixIot4G")
        or (command.startswith("ps | awk") and "{helloworld}" in command)
        or (command.startswith("netstat -nt") and ":1883" in command)
        or command.startswith("killall") and "phnixIot4G" in command
        or command.startswith("kill -STOP ")
        or command.startswith("kill -CONT ")
        or command.startswith("kill -TERM ")
        or command.startswith("kill -KILL ")
    )


def shell(command: str) -> tuple[int, bytes]:
    command = command.strip()

    # These queries need the virtual modem view rather than raw Debian process
    # names/paths.  Everything else is deliberately unrestricted.
    if _phnix_special(command):
        return work.shell(command)

    completed = subprocess.run(
        ["/bin/sh", "-c", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=120,
        env=os.environ.copy(),
    )
    return completed.returncode, completed.stdout


def main() -> int:
    # Keep the existing scenario/status CLI implementation.
    return work.main()


if __name__ == "__main__":
    raise SystemExit(main())
