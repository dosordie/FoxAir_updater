#!/usr/bin/env python3
"""Stable CLI for the autonomous DTU OTA backend (no GUI orchestration)."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

for candidate in (Path(__file__).resolve().parents[2], Path.cwd()):
    if (candidate / "updater/common/adb_transport.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from updater.common.adb_transport import AdbClient, TransportError
from updater.common.firmware_manifest import ManifestError
from updater.dtu_ota.client import DtuOtaClient, RunnerClientError
from updater.dtu_ota.package import PackageError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FoxAir autonomous DTU OTA backend client")
    parser.add_argument("--adb", default=shutil.which("adb") or "adb")
    parser.add_argument("--serial")
    parser.add_argument(
        "--adb-server-socket",
        help="optional remote ADB server, for example tcp:192.168.10.70:5038",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", aliases=["dry-run"], help="upload and verify only; never starts OTA")
    prepare.add_argument("--manifest", type=Path, required=True)
    prepare.add_argument("--firmware", type=Path)
    prepare.add_argument("--run-id")
    prepare.add_argument("--mode", choices=("full", "same-version"), default="full")
    prepare.add_argument("--restart-service-before-update", action="store_true")
    prepare.add_argument("--isolate-mqtt", action="store_true")

    start = commands.add_parser("start", help="start a prepared run detached on the DTU")
    start.add_argument("--run-id", required=True)
    for name in ("status", "log", "abort-request", "ack", "cleanup"):
        item = commands.add_parser(name)
        item.add_argument("--run-id")
    commands.add_parser("current", aliases=["active"])
    return parser


def main() -> int:
    args = build_parser().parse_args()
    env = None
    if args.adb_server_socket:
        env = os.environ.copy()
        env["ADB_SERVER_SOCKET"] = args.adb_server_socket
    client = DtuOtaClient(AdbClient(args.adb, args.serial, env=env))
    try:
        if args.command in {"prepare", "dry-run"}:
            value = client.prepare(
                manifest_path=args.manifest, firmware_path=args.firmware, run_id=args.run_id,
                mode=args.mode, restart_service_before_update=args.restart_service_before_update,
                isolate_mqtt=args.isolate_mqtt,
            )
        elif args.command == "start":
            value = client.start(args.run_id)
        elif args.command == "status":
            value = client.status(args.run_id)
        elif args.command == "log":
            print(client.log(args.run_id))
            return 0
        elif args.command == "abort-request":
            value = client.abort_request(args.run_id)
        elif args.command == "ack":
            value = client.acknowledge(args.run_id)
        elif args.command == "cleanup":
            client.cleanup(args.run_id)
            print(json.dumps({"ok": True, "cleaned": True}))
            return 0
        elif args.command == "current":
            run_id = client.current_run_id()
            value = client.status(run_id)
        elif args.command == "active":
            run_id = client.active_run_id()
            value = {"active": False, "run_id": None} if run_id is None else client.status(run_id)
        else:  # pragma: no cover - argparse guarantees this
            raise RunnerClientError("unsupported command")
        print(json.dumps(value, indent=2, ensure_ascii=False))
        return 0
    except (RunnerClientError, PackageError, ManifestError, TransportError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
