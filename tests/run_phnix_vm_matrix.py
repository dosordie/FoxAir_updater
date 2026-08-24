#!/usr/bin/env python3
"""End-to-end simulator matrix for the PHNIX controller entry point.

This intentionally runs the real controller process through an ADB-compatible
simulator instead of mocking AdbClient.  It therefore catches integration bugs
such as host parsing assumptions in `df` output.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SIMULATOR = REPO / "tools" / "phnix_ota" / "phnix_ota_simulator.py"
CONTROLLER = REPO / "tools" / "phnix_ota" / "phnix_local_ota_controller_hardened.py"

FULL_CASES = {
    "success": True,
    "parser-rejected": False,
    "crc-error": False,
    "metadata-mismatch": False,
    "offset-backwards": False,
    "offset-overflow": False,
    "stall-c350": False,
    "stall-c5a8": False,
    "helper-exit": False,
    "success-without-step12": False,
    "same-version": True,
}
HANDSHAKE_CASES = {
    "success": True,
    "wrong-status-1": False,
    "missing-status-2": False,
    "metadata-change": False,
    "c5a8-leak": False,
    "cancel-fail": False,
}
SAME_VERSION_CASES = {
    "success": True,
    "status-1": False,
    "c357-leak": False,
    "c5a8-leak": False,
    "restore-mismatch": False,
}


def run(command: list[str], env: dict[str, str], *, timeout: float = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def require_case(name: str, completed: subprocess.CompletedProcess[str], expected_success: bool) -> None:
    succeeded = completed.returncode == 0
    if succeeded != expected_success:
        expectation = "success" if expected_success else "failure"
        print(f"[FAIL] {name}: expected {expectation}, rc={completed.returncode}")
        print(completed.stdout)
        raise SystemExit(1)
    print(f"[PASS] {name}")


def reset_sim(env: dict[str, str], scenario: str = "success") -> None:
    completed = run([sys.executable, str(SIMULATOR), "reset", "--scenario", scenario], env)
    if completed.returncode != 0:
        print(completed.stdout)
        raise SystemExit("simulator reset failed")


def set_sim_mode(env: dict[str, str], mode: str, scenario: str) -> None:
    completed = run([sys.executable, str(SIMULATOR), mode, scenario], env)
    if completed.returncode != 0:
        print(completed.stdout)
        raise SystemExit(f"simulator {mode} failed")


def make_fixture(temp: Path) -> Path:
    firmware = temp / "VM_FW.bin"
    firmware.write_bytes((b"FoxAir PHNIX VM integration firmware\n" * 128)[:4096])
    raw = firmware.read_bytes()
    manifest = {
        "schema": "foxair-firmware-v1",
        "firmware_file": firmware.name,
        "software_code": "82400644",
        "display_version": "V3.3",
        "wire_version": "0033",
        "target_ssid": "0063",
        "size": len(raw),
        "md5": hashlib.md5(raw).hexdigest().upper(),
        "sha256": hashlib.sha256(raw).hexdigest().upper(),
        "image_base": "0x08050000",
    }
    path = temp / "VM_FW.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def main() -> int:
    total = len(FULL_CASES) + len(HANDSHAKE_CASES) + len(SAME_VERSION_CASES) + 2
    if total != 24:
        raise SystemExit(f"matrix definition changed unexpectedly: {total} cases")

    with tempfile.TemporaryDirectory(prefix="foxair-vm-matrix-") as temp_name:
        temp = Path(temp_name)
        env = os.environ.copy()
        env["PHNIX_OTA_SIM_HOME"] = str(temp / "sim-home")

        adb = temp / "sim-adb"
        adb.write_text(
            "#!/bin/sh\n"
            f"exec {sys.executable!s} {SIMULATOR!s} adb \"$@\"\n",
            encoding="utf-8",
        )
        adb.chmod(0o755)
        manifest = make_fixture(temp)
        state_dir = temp / "state"

        started = run([sys.executable, str(SIMULATOR), "start", "--scenario", "success"], env)
        if started.returncode != 0:
            print(started.stdout)
            return 1

        # reset_state() intentionally preloads a simulated helper because many
        # lab scenarios expect it.  `status` instead proves the clean original
        # runtime, so remove that fixture exactly as a completed OTA cleanup would.
        clean = run(
            [
                str(adb), "shell",
                "rm -f /data/phnix_ota_runtime_hook /data/.phnix_ota_runtime_hook.new",
            ],
            env,
        )
        if clean.returncode != 0:
            print(clean.stdout)
            return 1

        # 1: read-only status from a clean original-runtime state.
        completed = run(
            [sys.executable, str(CONTROLLER), "--adb", str(adb), "run", "--check", "status"],
            env,
        )
        require_case("status", completed, True)

        # 2: generic pre-C5A8 restore on the simulator
        reset_sim(env)
        completed = run(
            [sys.executable, str(CONTROLLER), "--adb", str(adb), "run", "--restore", "original"],
            env,
        )
        require_case("restore-original", completed, True)

        # 11 full-update state-machine scenarios.
        for scenario, expected_success in FULL_CASES.items():
            reset_sim(env, scenario)
            completed = run(
                [
                    sys.executable,
                    str(CONTROLLER),
                    "--adb",
                    str(adb),
                    "run",
                    "--manifest",
                    str(manifest),
                    "--execute",
                    "--confirm",
                    "VM-FULL-UPDATE",
                    "--state-dir",
                    str(state_dir / f"full-{scenario}"),
                    "--poll-interval",
                    "0.05",
                    "--start-timeout",
                    "0.8",
                    "--handshake-timeout",
                    "0.8",
                ],
                env,
                timeout=15,
            )
            require_case(f"full/{scenario}", completed, expected_success)

        # 6 hard-stop-before-C5A8 handshake/cancel scenarios.
        for scenario, expected_success in HANDSHAKE_CASES.items():
            reset_sim(env)
            set_sim_mode(env, "handshake-scenario", scenario)
            completed = run(
                [
                    sys.executable,
                    str(CONTROLLER),
                    "--adb",
                    str(adb),
                    "pre-c5a8-vm-test",
                    "--manifest",
                    str(manifest),
                    "--execute",
                    "--confirm",
                    "VM-PRE-C5A8-ONLY",
                ],
                env,
                timeout=10,
            )
            require_case(f"pre-c5a8/{scenario}", completed, expected_success)

        # 5 same-version proof scenarios.
        for scenario, expected_success in SAME_VERSION_CASES.items():
            reset_sim(env)
            set_sim_mode(env, "same-version-scenario", scenario)
            completed = run(
                [
                    sys.executable,
                    str(CONTROLLER),
                    "--adb",
                    str(adb),
                    "same-version-test",
                    "--manifest",
                    str(manifest),
                    "--execute",
                    "--confirm",
                    "VM-SAME-VERSION-ONLY",
                    "--state-dir",
                    str(state_dir / f"same-{scenario}"),
                    "--poll-interval",
                    "0.05",
                    "--timeout",
                    "1.5",
                ],
                env,
                timeout=10,
            )
            require_case(f"same-version/{scenario}", completed, expected_success)

        stopped = run([sys.executable, str(SIMULATOR), "stop"], env)
        if stopped.returncode != 0:
            print(stopped.stdout)
            return 1

    print("[OK] PHNIX VM matrix: 24/24 scenarios matched expected outcome")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
