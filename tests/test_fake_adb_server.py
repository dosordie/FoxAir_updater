import asyncio
import importlib.util
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


SERVER_PATH = Path("tools/testvm/fake_adb/foxair_fake_adb_server.py")
ADAPTER_PATH = Path("tools/testvm/fake_adb/qemu_lab_adapter.py")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_server_module():
    return load_module(SERVER_PATH, "foxair_fake_adb_server_tested")


def load_adapter_module():
    return load_module(ADAPTER_PATH, "foxair_qemu_lab_adapter_tested")


def find_real_adb() -> str | None:
    direct = shutil.which("adb") or shutil.which("adb.exe")
    if direct:
        return direct
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(variable)
        if not value:
            continue
        candidate = Path(value) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
        if candidate.is_file():
            return str(candidate)
    return None


def create_qemu_rootfs(root: Path, service: bytes = b"real-qemu-arm-service") -> Path:
    rootfs = root / "rootfs"
    for name in ("data", "cache", "tmp", "usr/bin", "bin"):
        (rootfs / name).mkdir(parents=True, exist_ok=True)
    (rootfs / "data/phnixIot4G").write_bytes(service)
    return rootfs.resolve()


class FakeSim:
    """Protocol-only backend; QEMU mapping itself is tested separately below."""

    def __init__(self, root: Path):
        self.home = root / "simulator"
        self.root = self.home / "root"
        for name in ("data", "cache", "tmp", "usr/bin"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "started").touch()
        (self.root / "data/phnixIot4G").write_bytes(b"fake-service")

    def sim_home(self):
        return self.home

    def root_path(self, remote: str):
        return self.root if remote == "/" else self.root / remote.lstrip("/")

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
        await send_request(writer, "host:tport:any")
        self.assertEqual(await reader.readexactly(4), b"OKAY")
        self.assertEqual(struct.unpack("<Q", await reader.readexactly(8))[0], 1)
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


class QemuLabAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lab = self.root / "phnix-lab"
        self.rootfs = create_qemu_rootfs(self.lab, b"ORIGINAL-ARM-PHNIX")
        self.state = self.root / "state"
        self.env = {
            "FOXAIR_QEMU_LAB_ROOT": str(self.lab),
            "FOXAIR_QEMU_LAB_ROOTFS": str(self.rootfs),
            "FOXAIR_FAKE_ADB_STATE": str(self.state),
            "FOXAIR_QEMU_FAKE_PID": "4100",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_adb_paths_are_the_existing_qemu_rootfs(self):
        with mock.patch.dict(os.environ, self.env, clear=False):
            adapter = load_adapter_module()
            self.assertEqual(adapter.root_path("/"), self.rootfs)
            self.assertEqual(adapter.root_path("/data/phnixIot4G"), self.rootfs / "data/phnixIot4G")
            self.assertEqual(adapter.shell("pidof phnixIot4G || true"), (0, b"4100\n"))
            self.assertEqual(adapter.shell("cat /data/phnixIot4G"), (0, b"ORIGINAL-ARM-PHNIX"))

    def test_reset_never_rebuilds_or_replaces_qemu_rootfs(self):
        service = self.rootfs / "data/phnixIot4G"
        before = service.read_bytes()
        with mock.patch.dict(os.environ, self.env, clear=False):
            adapter = load_adapter_module()
            adapter.reset_state("success", "success")
            self.assertEqual(service.read_bytes(), before)
            self.assertTrue((self.state / "qemu-adb/started").is_file())
            control = json.loads((self.lab / "control/foxair-ota-scenario.json").read_text())
            self.assertEqual(control["scenario"], "success")
            self.assertEqual(Path(control["rootfs"]), self.rootfs)

    def test_scenario_without_control_endpoint_fails_honestly_but_writes_contract(self):
        with mock.patch.dict(os.environ, self.env, clear=False):
            adapter = load_adapter_module()
            ok, message = adapter.apply_control("scenario", "stall-c5a8")
            self.assertFalse(ok)
            self.assertIn("kein QEMU/Mainboard-Control-Hook", message)
            control = json.loads((self.lab / "control/foxair-ota-scenario.json").read_text())
            self.assertEqual(control["scenario"], "stall-c5a8")

    @unittest.skipIf(os.name == "nt", "POSIX executable hook contract")
    def test_existing_qemu_scenario_hook_is_invoked(self):
        hook = self.lab / "tools/foxair-scenarioctl"
        hook.parent.mkdir(parents=True)
        hook.write_text(
            "#!/bin/sh\nprintf '%s %s\\n' \"$1\" \"$2\" > \"$FOXAIR_QEMU_LAB_ROOT/hook-called\"\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        with mock.patch.dict(os.environ, self.env, clear=False):
            adapter = load_adapter_module()
            ok, _message = adapter.apply_control("same-version-scenario", "c357-leak")
            self.assertTrue(ok)
            self.assertEqual((self.lab / "hook-called").read_text().strip(), "same-version-scenario c357-leak")


class RealAdbInteropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adb = find_real_adb()
        if not cls.adb:
            raise unittest.SkipTest("Google adb/platform-tools not installed on this runner")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.lab = cls.root / "phnix-lab"
        cls.rootfs = create_qemu_rootfs(cls.lab, b"REAL-QEMU-ROOTFS-SERVICE")
        cls.state_root = cls.root / "state"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.env = os.environ.copy()
        cls.env.update(
            {
                "ADB_SERVER_SOCKET": f"tcp:127.0.0.1:{cls.port}",
                "FOXAIR_QEMU_LAB_ROOT": str(cls.lab),
                "FOXAIR_QEMU_LAB_ROOTFS": str(cls.rootfs),
                "FOXAIR_FAKE_ADB_STATE": str(cls.state_root),
                "FOXAIR_QEMU_FAKE_PID": "4100",
            }
        )
        cls.server_process = subprocess.Popen(
            [
                sys.executable,
                str(SERVER_PATH),
                "--bind", "127.0.0.1",
                "--port", str(cls.port),
                "--state-root", str(cls.state_root),
                "--simulator", str(ADAPTER_PATH),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=cls.env,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if cls.server_process.poll() is not None:
                stdout, stderr = cls.server_process.communicate()
                raise RuntimeError(f"fake adb server exited early:\n{stdout}\n{stderr}")
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            cls.server_process.terminate()
            raise RuntimeError("fake adb server did not open its TCP port")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "server_process", None):
            cls.server_process.terminate()
            try:
                cls.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.server_process.kill()
                cls.server_process.wait(timeout=5)
        if getattr(cls, "tmp", None):
            cls.tmp.cleanup()

    def adb_run(self, *args: str, binary: bool = False):
        return subprocess.run(
            [self.adb, *args],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=not binary,
            timeout=15,
            check=False,
        )

    def test_real_adb_devices_shell_push_and_pull_hit_qemu_rootfs(self):
        devices = self.adb_run("devices", "-l")
        self.assertEqual(devices.returncode, 0, devices.stderr)
        self.assertIn("foxair-vm", devices.stdout)
        self.assertIn("device", devices.stdout)

        state = self.adb_run("get-state")
        self.assertEqual(state.returncode, 0, state.stderr)
        self.assertEqual(state.stdout.strip(), "device")

        shell = self.adb_run("shell", "pidof phnixIot4G || true")
        self.assertEqual(shell.returncode, 0, shell.stderr)
        self.assertEqual(shell.stdout.strip(), "4100")

        service = self.adb_run("shell", "cat /data/phnixIot4G", binary=True)
        self.assertEqual(service.returncode, 0, service.stderr.decode(errors="replace"))
        self.assertEqual(service.stdout, b"REAL-QEMU-ROOTFS-SERVICE")

        payload = b"real-adb-sync-test\x00FoxAir"
        local = self.root / "push.bin"
        pulled = self.root / "pull.bin"
        local.write_bytes(payload)
        push = self.adb_run("push", str(local), "/data/real-adb-sync-test.bin")
        self.assertEqual(push.returncode, 0, push.stderr)
        self.assertEqual((self.rootfs / "data/real-adb-sync-test.bin").read_bytes(), payload)

        pull = self.adb_run("pull", "/data/real-adb-sync-test.bin", str(pulled))
        self.assertEqual(pull.returncode, 0, pull.stderr)
        self.assertEqual(pulled.read_bytes(), payload)


class FakeAdbSourceContractTests(unittest.TestCase):
    def test_installer_requires_existing_qemu_lab_and_removes_python_backend(self):
        installer = Path("tools/testvm/fake_adb/install.sh").read_text(encoding="utf-8")
        self.assertIn("$ROOTFS/data/phnixIot4G", installer)
        self.assertIn("tools/testvm/fake_adb/qemu_lab_adapter.py", installer)
        self.assertIn("FOXAIR_FAKE_ADB_SIMULATOR=$INSTALL_DIR/qemu_lab_adapter.py", installer)
        self.assertNotIn("tools/phnix_ota/phnix_ota_simulator.py", installer)
        self.assertIn("legacy-python-simulator", installer)
        self.assertIn("systemctl enable --now foxair-fake-adb.service", installer)

    def test_service_can_access_existing_qemu_rootfs(self):
        unit = Path("tools/testvm/fake_adb/foxair-fake-adb.service").read_text(encoding="utf-8")
        self.assertIn("User=root", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("/opt/phnix-lab", unit)

    def test_ctl_routes_scenarios_to_qemu_adapter(self):
        source = Path("tools/testvm/fake_adb/foxair-fake-adbctl").read_text(encoding="utf-8")
        self.assertIn("qemu_lab_adapter.py", source)
        self.assertIn("adapter \"$cmd\" \"$1\"", source)
        self.assertIn("beendet NICHT phnixIot4G/QEMU", source)


if __name__ == "__main__":
    unittest.main()
