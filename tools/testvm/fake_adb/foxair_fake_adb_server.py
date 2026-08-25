#!/usr/bin/env python3
"""Minimal ADB smart-socket server for the FoxAir/PHNIX test VM.

The server intentionally implements only the host/device services used by the
FoxAir updater and its Windows GUI. It speaks to the *real* Google adb client
through ADB_SERVER_SOCKET=tcp:<vm>:5038 and maps device-side operations onto the
existing deterministic PHNIX OTA simulator.

This is a lab test service. It does not implement ADB authentication and should
only be exposed on an isolated/private test network.
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
from types import ModuleType

ADB_SERVER_VERSION = "0029"  # ADB_SERVER_VERSION 41, rendered as hex.
TRANSPORT_ID = 1
DEFAULT_BIND = os.environ.get("FOXAIR_FAKE_ADB_BIND", "0.0.0.0")
DEFAULT_PORT = int(os.environ.get("FOXAIR_FAKE_ADB_PORT", "5038"))
DEFAULT_SERIAL = os.environ.get("FOXAIR_FAKE_ADB_SERIAL", "foxair-vm")
DEFAULT_STATE = Path(os.environ.get("FOXAIR_FAKE_ADB_STATE", "/var/lib/foxair-fake-adb"))
DEFAULT_SIMULATOR = Path(
    os.environ.get(
        "FOXAIR_FAKE_ADB_SIMULATOR",
        str(Path(__file__).with_name("phnix_ota_simulator.py")),
    )
)
DEVICE_FEATURES = "shell_v2"
LOG = logging.getLogger("foxair-fake-adb")


class ProtocolError(RuntimeError):
    pass


def load_simulator(path: Path, state_root: Path) -> ModuleType:
    os.environ["PHNIX_OTA_SIM_HOME"] = str(state_root / "simulator")
    spec = importlib.util.spec_from_file_location("foxair_phnix_ota_simulator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Simulator kann nicht geladen werden: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def protocol_string(value: str | bytes) -> bytes:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return f"{len(raw):04x}".encode("ascii") + raw


async def read_exact(reader: asyncio.StreamReader, size: int) -> bytes:
    try:
        return await reader.readexactly(size)
    except asyncio.IncompleteReadError as exc:
        raise EOFError from exc


async def read_smart_request(reader: asyncio.StreamReader) -> str:
    header = await read_exact(reader, 4)
    try:
        length = int(header.decode("ascii"), 16)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ProtocolError(f"Ungültiger Smart-Socket-Header: {header!r}") from exc
    if length < 0 or length > 1024 * 1024:
        raise ProtocolError(f"Unplausible Smart-Socket-Länge: {length}")
    return (await read_exact(reader, length)).decode("utf-8", errors="strict")


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
        path = self.sim.root_path(remote)
        root = self.sim.root_path("/").resolve()
        resolved_parent = path.parent.resolve()
        if root != resolved_parent and root not in resolved_parent.parents:
            raise ValueError("Remote-Pfad verlässt die Simulator-Sandbox")
        return path

    def generic_file_shell(self, command: str) -> tuple[int, bytes] | None:
        """Handle generic file commands introduced by the Windows wrapper/GUI.

        The deterministic OTA simulator deliberately only recognizes commands it
        needs for OTA scenarios. This small layer adds safe sandboxed file
        primitives used by backup/cache tooling without executing arbitrary host
        shell commands on the Debian VM.
        """
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

    async def select_transport(
        self,
        writer: asyncio.StreamWriter,
        *,
        modern: bool,
        serial: str | None = None,
    ) -> tuple[bool, bool]:
        if serial is not None and serial != self.serial:
            await send_fail(writer, f"device '{serial}' not found")
            return True, False
        if not self.transport_available():
            await send_fail(writer, "device offline")
            return True, False
        await send_okay(writer)
        if modern:
            # Modern adb uses host:tport:* and requires the selected TransportId
            # immediately after OKAY. AOSP TransportId is uint64_t.
            writer.write(struct.pack("<Q", TRANSPORT_ID))
            await writer.drain()
        return True, True

    async def host_service(self, request: str, writer: asyncio.StreamWriter) -> tuple[bool, bool]:
        """Return (handled, transport_selected)."""
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
            # Keep the VM service alive. A normal matching-version client never
            # needs this; accepting it avoids a misleading protocol error.
            await send_okay(writer)
            return True, False

        # Current platform-tools uses the tport transport selector and expects
        # a binary 64-bit transport id after OKAY. Keep the legacy selector too
        # so old ADB clients remain usable against the test VM.
        if request in {"host:tport:any", "host:tport:usb", "host:tport:local"}:
            return await self.select_transport(writer, modern=True)
        if request.startswith("host:tport:serial:"):
            return await self.select_transport(
                writer,
                modern=True,
                serial=request.removeprefix("host:tport:serial:"),
            )
        if request in {"host:transport-any", "host:transport-usb", "host:transport-local"}:
            return await self.select_transport(writer, modern=False)
        if request.startswith("host:transport:"):
            return await self.select_transport(
                writer,
                modern=False,
                serial=request.removeprefix("host:transport:"),
            )
        if request == f"host:transport-id:{TRANSPORT_ID}":
            return await self.select_transport(writer, modern=False)

        for prefix, selector in (("host-serial:", self.serial), ("host-transport-id:", str(TRANSPORT_ID))):
            if request.startswith(prefix):
                rest = request[len(prefix):]
                selected, sep, sub = rest.partition(":")
                if not sep or selected != selector:
                    await send_fail(writer, "device not found")
                    return True, False
                value = {
                    "get-state": self.device_state(),
                    "get-serialno": self.serial,
                    "get-devpath": "usb:foxair-vm",
                    "features": DEVICE_FEATURES,
                }.get(sub)
                if value is None:
                    await send_fail(writer, f"unsupported host query: {sub}")
                else:
                    await send_query_response(writer, value)
                return True, False

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
        except Exception as exc:  # fail closed but keep protocol valid
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
        mode = st.st_mode
        size = st.st_size if path.is_file() else 0
        return mode, size, int(st.st_mtime)

    async def sync_service(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Serve classic ADB SYNC v1 until the client sends QUIT or closes.

        Modern adb keeps one SyncConnection open for several operations (for
        example STAT followed by RECV during pull), so this deliberately loops
        instead of assuming one request per TCP connection.
        """
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
                        writer.write(
                            b"DENT"
                            + struct.pack(
                                "<IIII",
                                st.st_mode,
                                st.st_size if child.is_file() else 0,
                                int(st.st_mtime),
                                len(name),
                            )
                            + name
                        )
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

            # SEND path is "remote,mode".
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
                request = await read_smart_request(reader)
                LOG.debug("%s -> %s", peer, request)
                handled, selected = await self.host_service(request, writer)
                if handled:
                    transport_selected = transport_selected or selected
                    if selected:
                        continue
                    return
                if not transport_selected:
                    await send_fail(writer, "device service requested before transport selection")
                    return
                if request.startswith("shell:") or request.startswith("shell,v2"):
                    await self.shell_service(request, writer)
                    return
                if request == "sync:":
                    await self.sync_service(reader, writer)
                    return
                if request.startswith("reconnect"):
                    await send_okay(writer)
                    return
                await send_fail(writer, f"unsupported device service: {request}")
                return
        except EOFError:
            pass
        except Exception:
            LOG.exception("ADB connection error from %s", peer)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def run(self) -> None:
        server = await asyncio.start_server(self.handle_client, self.bind, self.port)
        sockets = ", ".join(str(sock.getsockname()) for sock in (server.sockets or []))
        LOG.info("FoxAir Fake ADB listening on %s (serial=%s, features=%s)", sockets, self.serial, DEVICE_FEATURES)
        async with server:
            await server.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FoxAir PHNIX fake ADB smart-socket server")
    parser.add_argument("--bind", default=DEFAULT_BIND)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--serial", default=DEFAULT_SERIAL)
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--simulator", type=Path, default=DEFAULT_SIMULATOR)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args.state_root.mkdir(parents=True, exist_ok=True)
    server = FakeAdbServer(
        bind=args.bind,
        port=args.port,
        serial=args.serial,
        state_root=args.state_root,
        simulator_path=args.simulator,
    )
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
