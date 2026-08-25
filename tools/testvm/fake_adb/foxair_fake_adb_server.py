#!/usr/bin/env python3
"""Minimal ADB Smart Socket server for FoxAir TestVM integration.

The protocol layer intentionally knows nothing about the concrete modem
filesystem. The selected backend owns path mapping (QEMU rootfs, dedicated ADB
/tmp, etc.) and must reject paths it considers invalid.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import logging
import os
import re
import shlex
import struct
import sys
from pathlib import Path

ADB_SERVER_VERSION = "0029"
DEVICE_FEATURES = "shell_v2"
TRANSPORT_ID = 1
LOG = logging.getLogger("foxair-fake-adb")


class ProtocolError(RuntimeError):
    pass


def load_simulator(path: Path, state_root: Path):
    spec = importlib.util.spec_from_file_location("foxair_fake_adb_backend", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Backend nicht ladbar: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def read_exact(reader: asyncio.StreamReader, length: int) -> bytes:
    try:
        return await reader.readexactly(length)
    except asyncio.IncompleteReadError as exc:
        raise EOFError from exc


async def read_request(reader: asyncio.StreamReader) -> str:
    raw_length = await read_exact(reader, 4)
    try:
        length = int(raw_length.decode("ascii"), 16)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProtocolError("Ungültige ADB Request-Länge") from exc
    return (await read_exact(reader, length)).decode("utf-8")


def protocol_string(value: str | bytes) -> bytes:
    raw = value.encode() if isinstance(value, str) else value
    return f"{len(raw):04x}".encode("ascii") + raw


async def send_okay(writer: asyncio.StreamWriter) -> None:
    writer.write(b"OKAY")
    await writer.drain()


async def send_fail(writer: asyncio.StreamWriter, message: str) -> None:
    writer.write(b"FAIL" + protocol_string(message))
    await writer.drain()


async def send_query_response(writer: asyncio.StreamWriter, value: str | bytes) -> None:
    writer.write(b"OKAY" + protocol_string(value))
    await writer.drain()


def shell_packet(packet_id: int, payload: bytes) -> bytes:
    return bytes((packet_id,)) + struct.pack("<I", len(payload)) + payload


class FakeAdbServer:
    def __init__(self, *, bind: str, port: int, serial: str, state_root: Path, simulator_path: Path):
        self.bind = bind
        self.port = port
        self.serial = serial
        self.state_root = state_root
        self.sim = load_simulator(simulator_path, state_root)
        self.ensure_started()

    def ensure_started(self) -> None:
        home = self.sim.sim_home()
        home.mkdir(parents=True, exist_ok=True)
        if not (home / "started").exists():
            self.sim.reset_state("success", "success")
            (home / "started").touch()
        LOG.info("Simulator state: %s", home)

    def device_state(self) -> str:
        return "device" if (self.sim.sim_home() / "started").exists() else "offline"

    def device_line(self, long: bool = False) -> str:
        state = self.device_state()
        if not long:
            return f"{self.serial}\t{state}\n"
        return (
            f"{self.serial}\t{state} product:foxair model:LTE_VM "
            f"device:foxair transport_id:{TRANSPORT_ID}\n"
        )

    def transport_available(self) -> bool:
        return self.device_state() == "device"

    def remote_path(self, remote: str) -> Path:
        if not remote.startswith("/"):
            raise ValueError("Nur absolute Remote-Pfade werden unterstützt")
        # The backend is the authority for the virtual device namespace. This is
        # required by the Work-QEMU backend where /data and /cache live in the
        # QEMU rootfs while /tmp lives in a separate fake-ADB state directory.
        return self.sim.root_path(remote)

    def generic_file_shell(self, command: str) -> tuple[int, bytes] | None:
        match = re.fullmatch(
            r"if \[ -f ['\"](?P<path>/[^'\"]+)['\"] \]; then echo PRESENT; else echo ABSENT; fi",
            command,
        )
        if match:
            return 0, (b"PRESENT\n" if self.remote_path(match.group("path")).is_file() else b"ABSENT\n")

        match = re.fullmatch(r"test -(?:f|e) ['\"]?(?P<path>/[^;'\"]+)['\"]?; echo \$\?", command)
        if match:
            return 0, (b"0\n" if self.remote_path(match.group("path")).exists() else b"1\n")

        match = re.fullmatch(
            r"(?P<algo>sha256sum|md5sum) ['\"]?(?P<path>/[^|'\"]+)['\"]? \| awk '\{print \$1\}'",
            command,
        )
        if match:
            path = self.remote_path(match.group("path").strip())
            if not path.is_file():
                return 1, b""
            algo = "sha256" if match.group("algo") == "sha256sum" else "md5"
            digest = hashlib.new(algo, path.read_bytes()).hexdigest()
            return 0, (digest + "\n").encode("ascii")

        match = re.fullmatch(
            r"mv(?: -f)? ['\"](?P<src>/[^'\"]+)['\"] ['\"](?P<dst>/[^'\"]+)['\"] && sync && "
            r"(?P<algo>sha256sum|md5sum) ['\"](?P=dst)['\"] \| awk '\{print \$1\}'",
            command,
        )
        if match:
            src = self.remote_path(match.group("src"))
            dst = self.remote_path(match.group("dst"))
            if not src.exists():
                return 1, b""
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.replace(dst)
            algo = "sha256" if match.group("algo") == "sha256sum" else "md5"
            digest = hashlib.new(algo, dst.read_bytes()).hexdigest()
            return 0, (digest + "\n").encode("ascii")

        match = re.fullmatch(r"rm -f (?P<paths>.+)", command)
        if match:
            try:
                values = shlex.split(match.group("paths"))
            except ValueError:
                return 2, b""
            if values and all(value.startswith("/") for value in values):
                for value in values:
                    self.remote_path(value).unlink(missing_ok=True)
                return 0, b""

        match = re.fullmatch(r"mv(?: -f)? (?P<src>/\S+) (?P<dst>/\S+)", command)
        if match:
            src = self.remote_path(match.group("src"))
            dst = self.remote_path(match.group("dst"))
            if not src.exists():
                return 1, b""
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.replace(dst)
            return 0, b""

        match = re.fullmatch(r"mkdir -p (?P<path>/\S+)", command)
        if match:
            self.remote_path(match.group("path")).mkdir(parents=True, exist_ok=True)
            return 0, b""

        match = re.fullmatch(r"ls -A (?P<path>/\S+) 2>/dev/null \|\| true", command)
        if match:
            path = self.remote_path(match.group("path"))
            if not path.is_dir():
                return 0, b""
            names = "\n".join(sorted(child.name for child in path.iterdir()))
            return 0, (names + ("\n" if names else "")).encode()

        return None

    def execute_shell(self, command: str) -> tuple[int, bytes]:
        generic = self.generic_file_shell(command)
        if generic is not None:
            return generic
        return self.sim.shell(command)

    async def select_transport(self, writer: asyncio.StreamWriter, *, modern: bool, serial: str | None = None) -> tuple[bool, bool]:
        if serial is not None and serial != self.serial:
            await send_fail(writer, f"device '{serial}' not found")
            return True, False
        if not self.transport_available():
            await send_fail(writer, "device offline")
            return True, False
        await send_okay(writer)
        if modern:
            writer.write(struct.pack("<Q", TRANSPORT_ID))
            await writer.drain()
        return True, True

    async def host_service(self, request: str, writer: asyncio.StreamWriter) -> tuple[bool, bool]:
        if request == "host:version":
            await send_query_response(writer, ADB_SERVER_VERSION)
            return True, False
        if request == "host:devices":
            await send_query_response(writer, self.device_line(False))
            return True, False
        if request == "host:devices-l":
            await send_query_response(writer, self.device_line(True))
            return True, False
        if request in {"host:get-state", "host:get-serialno"}:
            await send_query_response(writer, self.device_state() if request.endswith("get-state") else self.serial)
            return True, False
        if request in {"host:features", "host:host-features"}:
            await send_query_response(writer, DEVICE_FEATURES)
            return True, False
        if request in {"host:reconnect", "host:reconnect-offline"}:
            await send_query_response(writer, f"reconnecting {self.serial}\n")
            return True, False
        if request == "host:kill":
            await send_okay(writer)
            return True, False
        if request in {"host:tport:any", "host:tport:usb", "host:tport:local"}:
            return await self.select_transport(writer, modern=True)
        if request.startswith("host:tport:serial:"):
            return await self.select_transport(writer, modern=True, serial=request.removeprefix("host:tport:serial:"))
        if request in {"host:transport-any", "host:transport-usb", "host:transport-local"}:
            return await self.select_transport(writer, modern=False)
        if request.startswith("host:transport:"):
            return await self.select_transport(writer, modern=False, serial=request.removeprefix("host:transport:"))
        if request == f"host:transport-id:{TRANSPORT_ID}":
            return await self.select_transport(writer, modern=False)
        return False, False

    async def shell_service(self, request: str, writer: asyncio.StreamWriter) -> None:
        shell_v2 = request.startswith("shell,v2")
        if shell_v2:
            _, sep, command = request.partition(":")
            if not sep:
                await send_fail(writer, "invalid shell,v2 request")
                return
        elif request.startswith("shell:"):
            command = request[len("shell:"):]
        else:
            await send_fail(writer, "unsupported shell service")
            return
        try:
            code, output = self.execute_shell(command)
        except KeyboardInterrupt:
            code, output = 130, b""
        except Exception as exc:
            LOG.exception("shell failed: %s", command)
            code, output = 1, (f"fake-adb shell error: {exc}\n").encode()
        await send_okay(writer)
        if shell_v2:
            if output:
                packet_id = 1 if code == 0 else 2
                writer.write(shell_packet(packet_id, output))
            writer.write(shell_packet(3, bytes((code & 0xFF,))))
        else:
            writer.write(output)
        await writer.drain()

    def sync_stat(self, remote: str) -> tuple[int, int, int]:
        try:
            path = self.remote_path(remote)
        except ValueError:
            return 0, 0, 0
        if not path.exists():
            return 0, 0, 0
        st = path.stat()
        return st.st_mode, st.st_size if path.is_file() else 0, int(st.st_mtime)

    async def sync_service(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await send_okay(writer)
        while True:
            try:
                header = await read_exact(reader, 8)
            except EOFError:
                return
            req_id = header[:4]
            length = struct.unpack("<I", header[4:])[0]
            if req_id == b"QUIT":
                return
            if req_id not in {b"STAT", b"LIST", b"RECV", b"SEND"}:
                message = b"unsupported sync request"
                writer.write(b"FAIL" + struct.pack("<I", len(message)) + message)
                await writer.drain()
                return
            raw_name = await read_exact(reader, length)
            remote_spec = raw_name.decode("utf-8", errors="strict")
            if req_id == b"STAT":
                mode, size, mtime = self.sync_stat(remote_spec)
                writer.write(b"STAT" + struct.pack("<III", mode, size, mtime))
                await writer.drain()
                continue
            if req_id == b"LIST":
                path = self.remote_path(remote_spec)
                if path.is_dir():
                    for child in sorted(path.iterdir(), key=lambda p: p.name):
                        st = child.stat()
                        name = child.name.encode("utf-8")
                        writer.write(b"DENT" + struct.pack("<IIII", st.st_mode, st.st_size if child.is_file() else 0, int(st.st_mtime), len(name)) + name)
                writer.write(b"DONE" + struct.pack("<I", 0))
                await writer.drain()
                continue
            if req_id == b"RECV":
                path = self.remote_path(remote_spec)
                if not path.is_file():
                    message = f"remote object '{remote_spec}' does not exist".encode()
                    writer.write(b"FAIL" + struct.pack("<I", len(message)) + message)
                    await writer.drain()
                    continue
                with path.open("rb") as stream:
                    while True:
                        chunk = stream.read(64 * 1024)
                        if not chunk:
                            break
                        writer.write(b"DATA" + struct.pack("<I", len(chunk)) + chunk)
                        await writer.drain()
                writer.write(b"DONE" + struct.pack("<I", 0))
                await writer.drain()
                continue
            remote, comma, mode_text = remote_spec.rpartition(",")
            if not comma or not remote.startswith("/"):
                message = b"invalid SEND path"
                writer.write(b"FAIL" + struct.pack("<I", len(message)) + message)
                await writer.drain()
                continue
            try:
                mode = int(mode_text, 10)
            except ValueError:
                mode = 0o644
            destination = self.remote_path(remote)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp = destination.with_name(destination.name + ".fake-adb-upload")
            try:
                mtime = 0
                with temp.open("wb") as stream:
                    while True:
                        packet = await read_exact(reader, 8)
                        packet_id = packet[:4]
                        value = struct.unpack("<I", packet[4:])[0]
                        if packet_id == b"DATA":
                            if value > 64 * 1024:
                                raise ProtocolError("SYNC DATA chunk > 64 KiB")
                            stream.write(await read_exact(reader, value))
                        elif packet_id == b"DONE":
                            mtime = value
                            break
                        else:
                            raise ProtocolError(f"Unexpected SEND packet: {packet_id!r}")
                temp.replace(destination)
                try:
                    os.chmod(destination, mode & 0o7777)
                except OSError:
                    pass
                if mtime:
                    try:
                        os.utime(destination, (mtime, mtime))
                    except OSError:
                        pass
                writer.write(b"OKAY" + struct.pack("<I", 0))
            except Exception as exc:
                temp.unlink(missing_ok=True)
                message = str(exc).encode("utf-8", errors="replace")
                writer.write(b"FAIL" + struct.pack("<I", len(message)) + message)
            await writer.drain()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        transport_selected = False
        try:
            while True:
                try:
                    request = await read_request(reader)
                except EOFError:
                    return
                if not transport_selected:
                    handled, selected = await self.host_service(request, writer)
                    if handled:
                        # ADB host queries such as host:version, host:devices-l
                        # and host:features are one request per connection. The
                        # real adb client calls ReadOrderlyShutdown() after the
                        # protocol-string response and waits for EOF. Only a
                        # transport-selection request keeps the smart socket
                        # open for a following shell:/sync: service request.
                        if not selected:
                            return
                        transport_selected = True
                        continue
                if request.startswith("shell:") or request.startswith("shell,v2"):
                    await self.shell_service(request, writer)
                    return
                if request == "sync:":
                    if not transport_selected:
                        await send_fail(writer, "no transport selected")
                        return
                    await self.sync_service(reader, writer)
                    return
                await send_fail(writer, f"unsupported service: {request}")
                return
        except (EOFError, ConnectionResetError, BrokenPipeError):
            return
        except Exception:
            LOG.exception("client %s failed", peer)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


async def run_server(args) -> None:
    server_impl = FakeAdbServer(bind=args.bind, port=args.port, serial=args.serial, state_root=Path(args.state_root), simulator_path=Path(args.simulator))
    server = await asyncio.start_server(server_impl.handle_client, args.bind, args.port)
    sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    LOG.info("FoxAir Fake ADB listening on %s (serial=%s, features=%s)", sockets, args.serial, DEVICE_FEATURES)
    async with server:
        await server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description="FoxAir Fake ADB Smart Socket server")
    parser.add_argument("--bind", default=os.environ.get("FOXAIR_FAKE_ADB_BIND", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("FOXAIR_FAKE_ADB_PORT", "5038")))
    parser.add_argument("--serial", default=os.environ.get("FOXAIR_FAKE_ADB_SERIAL", "foxair-vm"))
    parser.add_argument("--state-root", default=os.environ.get("FOXAIR_FAKE_ADB_STATE", "/var/lib/foxair-fake-adb"))
    parser.add_argument("--simulator", default=os.environ.get("FOXAIR_FAKE_ADB_SIMULATOR", str(Path(__file__).with_name("qemu_permissive_backend.py"))))
    parser.add_argument("--log-level", default=os.environ.get("FOXAIR_FAKE_ADB_LOG_LEVEL", "INFO"))
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(run_server(args))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())