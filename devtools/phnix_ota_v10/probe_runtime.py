#!/usr/bin/env python3
"""Read-only V1.0 runtime-state observation (never attaches GDB or sends OTA).

Uses the static V1.0 RAM candidates. A successfully read value is NOT proof that
the V1.0 hook is safe or that an update can be started.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from updater.common.adb_transport import AdbClient
from updater.common.phnix_modem_info import read_process_memory
from updater.dtu_ota.build_profiles import V10, identify_adb


def probe(client) -> dict:
    profile = identify_adb(client)
    if profile != V10:
        raise ValueError("Probe only permitted for exact pinned V1.0 build")
    raw_pids = client.shell("pidof phnixIot4G")
    pids = [word for word in raw_pids.split() if word.isdigit()]
    if len(pids) != 1:
        raise ValueError("expected exactly one phnixIot4G process")
    pid = int(pids[0])
    tracer = client.shell(
        f"awk '/^TracerPid:/ {{print $2}}' /proc/{pid}/status 2>/dev/null"
    )
    if tracer != "0":
        raise ValueError("target service is already traced or process state is unreadable")
    fields = {
        "dtu_run_step": profile.dtu_run_step,
        "dtu_sta": profile.dtu_sta,
        "board_ota_step": profile.board_ota_step,
        "uart_send_flag": profile.uart_send_flag,
    }
    result = {}
    for name, addr in fields.items():
        raw = read_process_memory(client, pid, addr, 1)
        if len(raw) != 1:
            raise ValueError(f"unreadable runtime state: {name} at 0x{addr:x}")
        result[name] = {"address": f"0x{addr:x}", "value": raw[0]}
    return {
        "build": V10.key,
        "pid": pid,
        "scope": "read-only static address validation; NOT OTA authorization",
        "values": result,
        "hypothesis_idle_v12_semantics": (
            result["dtu_run_step"]["value"] == 11
            and result["dtu_sta"]["value"] == 4
            and result["board_ota_step"]["value"] == 12
            and result["uart_send_flag"]["value"] == 0
        ),
        "ota_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default=shutil.which("adb") or "adb")
    parser.add_argument("--serial")
    parser.add_argument("--adb-server-socket", help="e.g. tcp:192.168.10.70:5038")
    args = parser.parse_args()
    env = None
    if args.adb_server_socket:
        env = os.environ.copy()
        env["ADB_SERVER_SOCKET"] = args.adb_server_socket
    try:
        result = probe(AdbClient(args.adb, args.serial, env=env))
    except (ValueError, OSError, RuntimeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
