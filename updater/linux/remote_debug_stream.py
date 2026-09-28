#!/usr/bin/env python3
"""Read-only TCP bridge for the PHNIX USB debug interface.

The FoxAir Windows updater expects the raw PHNIX debug stream on ADB-port + 1
(default TCP 5039). This helper deliberately never forwards TCP input back to
the modem. It discovers the SIMCom USB serial function by VID/PID/interface so
USB re-enumeration does not depend on a fixed /dev/ttyUSB number.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import termios
from pathlib import Path
from typing import Iterable

USB_VENDOR_ID = "1e0e"
USB_PRODUCT_ID = "9001"
USB_INTERFACE_NUM = "04"
DEFAULT_BIND = "0.0.0.0"
DEFAULT_PORT = 5039
RETRY_SECONDS = 2.0
MAX_CLIENT_BUFFER = 1024 * 1024


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="ascii").strip().lower()
    except OSError:
        return ""


def _device_identity(device: Path) -> tuple[str, str, str]:
    try:
        current = device.resolve()
    except OSError:
        current = device
    vendor = ""
    product = ""
    interface = ""
    for parent in (current, *current.parents):
        if not interface:
            interface = _read_text(parent / "bInterfaceNumber")
        if not vendor:
            vendor = _read_text(parent / "idVendor")
        if not product:
            product = _read_text(parent / "idProduct")
        if vendor and product and interface:
            break
    return vendor, product, interface


def discover_debug_ports(
    sys_class_tty: Path = Path("/sys/class/tty"),
    dev_root: Path = Path("/dev"),
) -> list[Path]:
    matches: list[Path] = []
    try:
        entries: Iterable[Path] = sys_class_tty.iterdir()
    except OSError:
        return matches
    for entry in entries:
        name = entry.name
        if not (name.startswith("ttyUSB") or name.startswith("ttyACM")):
            continue
        device = entry / "device"
        vendor, product, interface = _device_identity(device)
        if (
            vendor == USB_VENDOR_ID
            and product == USB_PRODUCT_ID
            and interface == USB_INTERFACE_NUM
        ):
            candidate = dev_root / name
            if candidate.exists():
                matches.append(candidate)
    return sorted(matches)


def discover_debug_port() -> Path | None:
    matches = discover_debug_ports()
    return matches[0] if len(matches) == 1 else None


def _configure_raw_read(fd: int) -> None:
    attrs = termios.tcgetattr(fd)
    attrs[0] &= ~(
        termios.IGNBRK
        | termios.BRKINT
        | termios.PARMRK
        | termios.ISTRIP
        | termios.INLCR
        | termios.IGNCR
        | termios.ICRNL
        | termios.IXON
        | termios.IXOFF
        | getattr(termios, "IXANY", 0)
    )
    attrs[1] &= ~termios.OPOST
    attrs[2] &= ~(termios.CSIZE | termios.PARENB | termios.CSTOPB)
    attrs[2] |= termios.CS8 | termios.CLOCAL | termios.CREAD
    if hasattr(termios, "CRTSCTS"):
        attrs[2] &= ~termios.CRTSCTS
    attrs[3] &= ~(
        termios.ECHO
        | getattr(termios, "ECHONL", 0)
        | termios.ICANON
        | termios.ISIG
        | getattr(termios, "IEXTEN", 0)
    )
    attrs[6][termios.VMIN] = 1
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


class DebugStreamServer:
    def __init__(self, bind: str, port: int):
        self.bind = bind
        self.port = port
        self.clients: set[asyncio.StreamWriter] = set()
        self.serial_fd: int | None = None
        self.serial_path: Path | None = None
        self.loop = asyncio.get_running_loop()

    def log(self, message: str) -> None:
        print(message, flush=True)

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        self.clients.add(writer)
        self.log(f"[client] connected: {peer}")
        try:
            while await reader.read(4096):
                pass
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self.clients.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, asyncio.CancelledError):
                pass
            self.log(f"[client] disconnected: {peer}")

    def _close_serial(self, reason: str) -> None:
        fd = self.serial_fd
        if fd is None:
            return
        try:
            self.loop.remove_reader(fd)
        except Exception:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
        self.serial_fd = None
        old_path = self.serial_path
        self.serial_path = None
        self.log(f"[serial] disconnected: {old_path or '?'} ({reason})")

    def _serial_ready(self) -> None:
        fd = self.serial_fd
        if fd is None:
            return
        try:
            payload = os.read(fd, 65536)
        except BlockingIOError:
            return
        except OSError as error:
            self._close_serial(str(error))
            return
        if not payload:
            self._close_serial("EOF")
            return

        stale: list[asyncio.StreamWriter] = []
        for writer in tuple(self.clients):
            transport = writer.transport
            if transport is None or transport.is_closing():
                stale.append(writer)
                continue
            if transport.get_write_buffer_size() > MAX_CLIENT_BUFFER:
                stale.append(writer)
                continue
            try:
                writer.write(payload)
            except (ConnectionError, RuntimeError):
                stale.append(writer)
        for writer in stale:
            self.clients.discard(writer)
            writer.close()

    def _try_open_serial(self) -> None:
        if self.serial_fd is not None:
            return
        path = discover_debug_port()
        if path is None:
            return
        fd: int | None = None
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
            _configure_raw_read(fd)
        except OSError as error:
            self.log(f"[serial] open failed for {path}: {error}")
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            return
        self.serial_fd = fd
        self.serial_path = path
        self.loop.add_reader(fd, self._serial_ready)
        self.log(f"[serial] connected: {path} (VID 1e0e PID 9001 IF 04)")

    async def serial_monitor(self) -> None:
        while True:
            if self.serial_fd is not None:
                path = self.serial_path
                if path is None or not path.exists():
                    self._close_serial("device disappeared")
            else:
                self._try_open_serial()
            await asyncio.sleep(RETRY_SECONDS)

    async def run(self) -> None:
        server = await asyncio.start_server(self.handle_client, self.bind, self.port)
        addresses = ", ".join(str(sock.getsockname()) for sock in server.sockets or ())
        self.log(f"[tcp] read-only PHNIX debug stream listening on {addresses}")
        monitor = asyncio.create_task(self.serial_monitor())
        try:
            async with server:
                await server.serve_forever()
        finally:
            monitor.cancel()
            self._close_serial("server stopping")
            for writer in tuple(self.clients):
                writer.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FoxAir read-only PHNIX debug TCP bridge"
    )
    parser.add_argument("--bind", default=DEFAULT_BIND)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--detect",
        action="store_true",
        help="print the currently detected PHNIX debug tty and exit",
    )
    return parser


async def _main_async(bind: str, port: int) -> None:
    server = DebugStreamServer(bind, port)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    serve_task = asyncio.create_task(server.run())
    stop_task = asyncio.create_task(stop.wait())
    done, _ = await asyncio.wait(
        {serve_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    if serve_task not in done:
        serve_task.cancel()
        try:
            await serve_task
        except asyncio.CancelledError:
            pass
    else:
        serve_task.result()
    stop_task.cancel()


def main() -> int:
    args = build_parser().parse_args()
    if args.detect:
        port = discover_debug_port()
        if port is None:
            print("not-found")
            return 1
        print(port)
        return 0
    if not 1 <= args.port <= 65535:
        raise SystemExit("invalid TCP port")
    asyncio.run(_main_async(args.bind, args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
