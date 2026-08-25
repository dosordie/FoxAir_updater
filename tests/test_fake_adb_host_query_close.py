import asyncio
import importlib.util
import tempfile
import unittest
from pathlib import Path


SERVER_PATH = Path("tools/testvm/fake_adb/foxair_fake_adb_server.py")


def load_server():
    spec = importlib.util.spec_from_file_location("foxair_fake_adb_host_close_tested", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeSim:
    def __init__(self, root: Path):
        self.home = root / "state"
        self.root = root / "root"
        self.home.mkdir(parents=True)
        self.root.mkdir(parents=True)
        (self.home / "started").touch()

    def sim_home(self):
        return self.home

    def root_path(self, remote: str):
        return self.root if remote == "/" else self.root / remote.lstrip("/")

    def shell(self, command: str):
        return 0, b""


async def send_request(writer, request: str):
    payload = request.encode()
    writer.write(f"{len(payload):04x}".encode() + payload)
    await writer.drain()


async def read_query(reader):
    assert await reader.readexactly(4) == b"OKAY"
    length = int((await reader.readexactly(4)).decode(), 16)
    return await reader.readexactly(length)


class HostQueryCloseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.module = load_server()
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.impl = object.__new__(self.module.FakeAdbServer)
        self.impl.bind = "127.0.0.1"
        self.impl.port = 0
        self.impl.serial = "foxair-vm"
        self.impl.state_root = root
        self.impl.sim = FakeSim(root)
        self.server = await asyncio.start_server(self.impl.handle_client, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        self.tmp.cleanup()

    async def connect(self):
        return await asyncio.open_connection("127.0.0.1", self.port)

    async def test_host_version_returns_payload_then_eof(self):
        reader, writer = await self.connect()
        await send_request(writer, "host:version")
        self.assertEqual(await read_query(reader), b"0029")
        self.assertEqual(await asyncio.wait_for(reader.read(), timeout=1), b"")
        writer.close()
        await writer.wait_closed()

    async def test_devices_l_returns_payload_then_eof(self):
        reader, writer = await self.connect()
        await send_request(writer, "host:devices-l")
        payload = await read_query(reader)
        self.assertIn(b"foxair-vm\tdevice", payload)
        self.assertEqual(await asyncio.wait_for(reader.read(), timeout=1), b"")
        writer.close()
        await writer.wait_closed()

    async def test_transport_selection_keeps_connection_open(self):
        reader, writer = await self.connect()
        await send_request(writer, "host:tport:any")
        self.assertEqual(await reader.readexactly(4), b"OKAY")
        self.assertEqual(len(await reader.readexactly(8)), 8)
        await send_request(writer, "shell,v2,raw:printf test")
        self.assertEqual(await reader.readexactly(4), b"OKAY")
        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    unittest.main()
