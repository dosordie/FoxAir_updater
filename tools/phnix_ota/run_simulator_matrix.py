#!/usr/bin/env python3
"""Run the OTA controller against every deterministic VM scenario."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


EXPECTED = {
    "success": (0, False),
    "same-version": (0, False),
    "parser-rejected": (1, False),
    "crc-error": (1, False),
    "metadata-mismatch": (1, False),
    "offset-backwards": (1, False),
    "offset-overflow": (1, False),
    "stall-c350": (1, True),
    "stall-c5a8": (1, False),
    "helper-exit": (1, True),
    "success-without-step12": (1, True),
}
CANCEL_EXPECTED = {
    "success": (0, False),
    "retry-success": (0, False),
    "no-response": (1, True),
    "rejected": (1, True),
    "wrong-ssid": (1, True),
    "c36c-only": (1, True),
}
HANDSHAKE_EXPECTED = {
    "success": (0, False),
    "wrong-status-1": (1, True),
    "missing-status-2": (1, True),
    "metadata-change": (1, True),
    "c5a8-leak": (1, True),
    "cancel-fail": (1, True),
}


def run(command: list[str], timeout: float = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sim", type=Path, default=Path("./phnix-ota-sim"))
    parser.add_argument("--adb", type=Path, default=Path("./phnix-sim-adb"))
    parser.add_argument("--controller", type=Path, default=Path("./phnix_local_ota_controller.py"))
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    args.sim = args.sim.resolve()
    args.adb = args.adb.resolve()
    args.controller = args.controller.resolve()
    args.firmware = args.firmware.resolve()
    results = []

    for scenario, (expected_rc, expected_hold) in EXPECTED.items():
        run([str(args.sim), "scenario", scenario])
        with tempfile.TemporaryDirectory(prefix=f"phnix-{scenario}-") as state_dir:
            completed = run([
                str(args.controller), "--adb", str(args.adb), "run",
                "--manifest", str(args.manifest), "--firmware", str(args.firmware), "--execute",
                "--confirm", "VM-FULL-UPDATE",
                "--state-dir", state_dir, "--poll-interval", "0.05",
                "--start-timeout", "3", "--handshake-timeout", "3",
                "--block-timeout", "1",
            ])
        status_result = run([str(args.sim), "status"])
        status = json.loads(status_result.stdout)
        expected_helper = expected_hold
        passed = (
            completed.returncode == expected_rc
            and status.get("held") is expected_hold
            and status.get("runtime_helper_present") is expected_helper
        )
        results.append({
            "scenario": scenario,
            "returncode": completed.returncode,
            "held": status.get("held"),
            "runtime_helper_present": status.get("runtime_helper_present"),
            "passed": passed,
        })
        print(json.dumps(results[-1]), flush=True)

    for scenario, (expected_rc, expected_hold) in CANCEL_EXPECTED.items():
        run([str(args.sim), "scenario", "stall-c350"])
        run([str(args.sim), "cancel-scenario", scenario])
        with tempfile.TemporaryDirectory(prefix=f"phnix-cancel-{scenario}-") as state_dir:
            prepare = run([
                str(args.controller), "--adb", str(args.adb), "run",
                "--manifest", str(args.manifest), "--firmware", str(args.firmware), "--execute",
                "--confirm", "VM-FULL-UPDATE",
                "--state-dir", state_dir, "--poll-interval", "0.05",
                "--start-timeout", "3", "--handshake-timeout", "3",
                "--block-timeout", "1",
            ])
            completed = run([
                str(args.controller), "--adb", str(args.adb), "cancel",
                "--execute", "--confirm", "CANCEL-PHNIX-OTA",
                "--poll-interval", "0.05", "--timeout", "1",
            ])
        status_result = run([str(args.sim), "status"])
        status = json.loads(status_result.stdout)
        passed = (
            prepare.returncode == 1
            and completed.returncode == expected_rc
            and status.get("held") is expected_hold
            and status.get("runtime_helper_present") is expected_hold
        )
        results.append({
            "scenario": f"cancel-{scenario}",
            "returncode": completed.returncode,
            "held": status.get("held"),
            "runtime_helper_present": status.get("runtime_helper_present"),
            "passed": passed,
        })
        print(json.dumps(results[-1]), flush=True)

    # Recovery must also work when the temporary helper is already absent:
    # install the verified local copy, restore, then remove it again.
    run([str(args.sim), "scenario", "success"])
    run([str(args.adb), "shell", "rm -f /data/phnix_ota_runtime_hook /data/.phnix_ota_runtime_hook.new"])
    completed = run([
        str(args.controller), "--adb", str(args.adb),
        "run", "--restore", "original",
    ])
    status_result = run([str(args.sim), "status"])
    status = json.loads(status_result.stdout)
    passed = (
        completed.returncode == 0
        and status.get("held") is False
        and status.get("runtime_helper_present") is False
    )
    results.append({
        "scenario": "restore-with-helper-absent",
        "returncode": completed.returncode,
        "held": status.get("held"),
        "runtime_helper_present": status.get("runtime_helper_present"),
        "passed": passed,
    })
    print(json.dumps(results[-1]), flush=True)

    for scenario, (expected_rc, expected_hold) in HANDSHAKE_EXPECTED.items():
        run([str(args.sim), "scenario", "success"])
        run([str(args.sim), "handshake-scenario", scenario])
        completed = run([
            str(args.controller), "--adb", str(args.adb), "pre-c5a8-vm-test",
            "--manifest", str(args.manifest), "--firmware", str(args.firmware), "--execute",
            "--confirm", "VM-PRE-C5A8-ONLY",
        ])
        status_result = run([str(args.sim), "status"])
        status = json.loads(status_result.stdout)
        passed = completed.returncode == expected_rc and status.get("held") is expected_hold
        results.append({
            "scenario": f"handshake-{scenario}",
            "returncode": completed.returncode,
            "held": status.get("held"),
            "passed": passed,
        })
        print(json.dumps(results[-1]), flush=True)

    failures = [item for item in results if not item["passed"]]
    print(json.dumps({"passed": len(results) - len(failures), "total": len(results),
                      "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
