import asyncio
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path


SERVER_PATH = Path("tools/testvm/fake_adb/foxair_fake_adb_server.py")


def load_server_module():
    spec = importlib.util.spec_from_file_location("foxair_fake_adb_server_tested", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeSim:
    def __init__(self, root: Path):
        self.home = root / "simulator"
        self.root = self.home / "root"
        for name in ("data", "cache", "tmp", "usr/bin"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.home / "started").parent.mkdir(parents=True, exist_ok=True)
        (self.home / "started").touch()
        (self.root / "data/phnixIot4G").write_bytes(b"fake-service")

    def sim_home(self):
        return self.home

    def root_path(self, remote: str):
        return self.root / remote.lstrip("/")

    def shell(self, command: str):
        if command == "pidof phnixIot4G || true":
            return 0, b"4100\n"
        if command.startswith("cat "):
            path = self.root_path(command[4:])
            return (0, path.read_bytes()) if path.exists() else (1, b"")
        return 1, ("unsupported: " + command + "\n").encode()


async def send_request(writer, payload: str):
    raw = payload.encode()
    writer.write(f"{len(raw):04x}".encode() + raw)
    await writer.drain()


async def read_query(reader):
    status = await reader.readexactly(4)
    if status == b"FAIL":
        length = int((await reader.readexactly(4)).decode(), 16)
        return status, await reader.readexactly(length)
    length = int((await reader.readexactly(4)).decode(), 16)
    return status, await reader.readexactly(length)


class FakeAdbServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.module = load_server_module()
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.fake = object.__new__(self.module.FakeAdbServer)
        self.fake.bind = "127.0.0.1"
        self.fake.port = 0
        self.fake.serial = "foxair-vm"
        self.fake.state_root = root
        self.fake.sim = FakeSim(root)
        self.server = await asyncio.start_server(self.fake.handle_client, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        self.tmp.cleanup()

    async def connect(self):
        return await asyncio.open_connection("127.0.0.1", self.port)

    async def test_host_version_and_devices(self):
        reader, writer = await self.connect()
        await send_request(writer, "host:version")
        status, payload = await read_query(reader)
        self.assertEqual(status, b"OKAY")
        self.assertEqual(payload, b"0029")
        writer.close()
        await writer.wait_closed()

        reader, writer = await self.connect()
        await send_request(writer, "host:devices-l")
        status, payload = await read_query(reader)
        self.assertEqual(status, b"OKAY")
        self.assertIn(b"foxair-vm\tdevice", payload)
        self.assertIn(b"transport_id:1", payload)
        writer.close()
        await writer.wait_closed()

    async def test_shell_v2_reports_output_and_exit_code(self):
        reader, writer = await self.connect()
        await send_request(writer, "host:transport-any")
        self.assertEqual(await reader.readexactly(4), b"OKAY")
        await send_request(writer, "shell,v2,raw:pidof phnixIot4G || true")
        self.assertEqual(await reader.readexactly(4), b"OKAY")

        packet_id = (await reader.readexactly(1))[0]
        length = struct.unpack("<I", await reader.readexactly(4))[0]
        payload = await reader.readexactly(length)
        self.assertEqual(packet_id, 1)
        self.assertEqual(payload, b"4100\n")

        exit_id = (await reader.readexactly(1))[0]
        exit_length = struct.unpack("<I", await reader.readexactly(4))[0]
        exit_payload = await reader.readexactly(exit_length)
        self.assertEqual(exit_id, 3)
        self.assertEqual(exit_payload, b"\x00")
        writer.close()
        await writer.wait_closed()

    async def test_sync_send_stat_and_recv(self):
        data = b"FoxAir fake ADB\x00binary\n"

        reader, writer = await self.connect()
        await send_request(writer, "host:transport-any")
        self.assertEqual(await reader.readexactly(4), b"OKAY")
        await send_request(writer, "sync:")
        self.assertEqual(await reader.readexactly(4), b"OKAY")
        remote = b"/data/test.bin,420"
        writer.write(b"SEND" + struct.pack("<I", len(remote)) + remote)
        writer.write(b"DATA" + struct.pack("<I", len(data)) + data)
        writer.write(b"DONE" + struct.pack("<I", int(1700000000)))
        await writer.drain()
        self.assertEqual(await reader.readexactly(4), b"OKAY")
        self.assertEqual(struct.unpack("<I", await reader.readexactly(4))[0], 0)
        writer.close()
        await writer.wait_closed()
        self.assertEqual(self.fake.sim.root_path("/data/test.bin").read_bytes(), data)

        reader, writer = await self.connect()
        await send_request(writer, "host:transport-any")
        self.assertEqual(await reader.readexactly(4), b"OKAY")
        await send_request(writer, "sync:")
        self.assertEqual(await reader.readexactly(4), b"OKAY")
        remote_path = b"/data/test.bin"

        # Real adb pull keeps one SyncConnection open and performs STAT before RECV.
        writer.write(b"STAT" + struct.pack("<I", len(remote_path)) + remote_path)
        await writer.drain()
        self.assertEqual(await reader.readexactly(4), b"STAT")
        mode, size, _mtime = struct.unpack("<III", await reader.readexactly(12))
        self.assertNotEqual(mode, 0)
        self.assertEqual(size, len(data))

        writer.write(b"RECV" + struct.pack("<I", len(remote_path)) + remote_path)
        await writer.drain()
        recv_id = await reader.readexactly(4)
        recv_len = struct.unpack("<I", await reader.readexactly(4))[0]
        recv_data = await reader.readexactly(recv_len)
        self.assertEqual(recv_id, b"DATA")
        self.assertEqual(recv_data, data)
        self.assertEqual(await reader.readexactly(4), b"DONE")
        await reader.readexactly(4)
        writer.close()
        await writer.wait_closed()

    async def test_current_windows_backup_probe_and_manual_cache_hash(self):
        cache = self.fake.sim.root_path("/cache/phnixIot_device_OTA")
        cache.write_bytes(b"firmware")
        code, output = self.fake.execute_shell(
            "if [ -f '/cache/phnixIot_device_OTA' ]; then echo PRESENT; else echo ABSENT; fi"
        )
        self.assertEqual((code, output), (0, b"PRESENT\n"))

        code, output = self.fake.execute_shell(
            "sha256sum '/cache/phnixIot_device_OTA' | awk '{print $1}'"
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(output.strip()), 64)

    async def test_simulator_stop_makes_device_offline(self):
        (self.fake.sim.sim_home() / "started").unlink()
        reader, writer = await self.connect()
        await send_request(writer, "host:get-state")
        status, payload = await read_query(reader)
        self.assertEqual(status, b"OKAY")
        self.assertEqual(payload, b"offline")
        writer.close()
        await writer.wait_closed()


class FakeAdbSourceContractTests(unittest.TestCase):
    def test_installer_is_one_command_and_uses_existing_simulator(self):
        installer = Path("tools/testvm/fake_adb/install.sh").read_text(encoding="utf-8")
        self.assertIn("tools/phnix_ota/phnix_ota_simulator.py", installer)
        self.assertIn("systemctl enable --now foxair-fake-adb.service", installer)
        self.assertIn("FOXAIR_FAKE_ADB_PORT=5038", installer)

    def test_service_runs_unprivileged(self):
        unit = Path("tools/testvm/fake_adb/foxair-fake-adb.service").read_text(encoding="utf-8")
        self.assertIn("User=foxair-adb", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("ReadWritePaths=/var/lib/foxair-fake-adb", unit)


if __name__ == "__main__":
    unittest.main()
