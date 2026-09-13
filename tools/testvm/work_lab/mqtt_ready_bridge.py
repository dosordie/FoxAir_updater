#!/usr/bin/env python3
"""Keep one namespace-visible MQTT connection for paused-QEMU preflight.

The production supervisor checks the modem's own network namespace before it
attaches its runtime hook. In the Work VM, qemu-user is intentionally stopped
at its remote-GDB entry point, while the supervisor runs in the Debian host
namespace. This lab-only client makes that host-side readiness check truthful
without changing the production hook or supervisor.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import ssl
import time
from pathlib import Path


STOP = False


def request_stop(_signum: int, _frame: object) -> None:
    global STOP
    STOP = True


def mqtt_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return len(encoded).to_bytes(2, "big") + encoded


def connect_packet(client_id: str) -> bytes:
    variable = mqtt_string("MQTT") + bytes((4, 2, 0, 30))
    payload = mqtt_string(client_id)
    body = variable + payload
    if len(body) >= 128:
        raise ValueError("MQTT readiness client id is too long")
    return bytes((0x10, len(body))) + body


def write_event(path: Path, event: str, **fields: object) -> None:
    record = {"time": time.time(), "event": event, **fields}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--ca", type=Path)
    parser.add_argument("--server-hostname")
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    client_id = f"foxair-vm-preflight-{os.getpid()}"
    try:
        deadline = time.monotonic() + 5.0
        while True:
            try:
                client = socket.create_connection((args.host, args.port), timeout=1.0)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        if args.ca:
            context = ssl.create_default_context(cafile=str(args.ca))
            client = context.wrap_socket(
                client, server_hostname=args.server_hostname or args.host
            )
        with client:
            client.settimeout(5.0)
            client.sendall(connect_packet(client_id))
            response = client.recv(4)
            if response != b"\x20\x02\x00\x00":
                write_event(args.transcript, "connack-rejected", response=response.hex())
                return 2
            args.ready_file.write_text(f"{os.getpid()}\n", encoding="ascii")
            write_event(args.transcript, "ready", client_id=client_id)
            while not STOP:
                time.sleep(10)
                if STOP:
                    break
                client.sendall(b"\xc0\x00")
                response = client.recv(2)
                if response != b"\xd0\x00":
                    write_event(args.transcript, "ping-failed", response=response.hex())
                    return 3
    except OSError as exc:
        write_event(args.transcript, "connection-failed", error=str(exc))
        return 1
    finally:
        args.ready_file.unlink(missing_ok=True)
    write_event(args.transcript, "stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
