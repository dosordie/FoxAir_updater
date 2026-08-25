import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


BACKEND_PATH = Path("tools/testvm/fake_adb/qemu_permissive_backend.py")


def load_backend():
    spec = importlib.util.spec_from_file_location("foxair_permissive_backend_tested", BACKEND_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PermissiveAdbBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lab = self.root / "phnix-lab"
        self.rootfs = self.lab / "rootfs"
        for directory in ("data", "cache", "tmp", "usr/bin"):
            (self.rootfs / directory).mkdir(parents=True, exist_ok=True)
        service = self.rootfs / "data/phnixIot4G"
        service.write_bytes(b"ORIGINAL")
        service.chmod(0o755)
        qemu = self.rootfs / "usr/bin/qemu-arm-static"
        qemu.write_bytes(b"qemu")
        qemu.chmod(0o755)
        self.state = self.root / "state"
        self.env = {
            "FOXAIR_QEMU_LAB_ROOT": str(self.lab),
            "FOXAIR_QEMU_LAB_ROOTFS": str(self.rootfs),
            "FOXAIR_FAKE_ADB_STATE": str(self.state),
            "FOXAIR_QEMU_FAKE_PID": "4100",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_unknown_shell_command_runs_through_host_shell(self):
        with mock.patch.dict(os.environ, self.env, clear=False):
            backend = load_backend()
            code, output = backend.shell("printf 'arbitrary-adb-shell-ok'")
        self.assertEqual(code, 0)
        self.assertEqual(output, b"arbitrary-adb-shell-ok")

    def test_shell_pipeline_is_not_allowlisted(self):
        with mock.patch.dict(os.environ, self.env, clear=False):
            backend = load_backend()
            code, output = backend.shell("printf 'a\\nb\\n' | awk 'NR == 2 {print}'")
        self.assertEqual(code, 0)
        self.assertEqual(output, b"b\n")

    def test_phnix_pid_still_uses_virtual_process_view(self):
        with mock.patch.dict(os.environ, self.env, clear=False):
            backend = load_backend()
            self.assertEqual(backend.shell("pidof phnixIot4G || true"), (0, b"4100\n"))

    def test_tmp_sync_path_matches_host_shell_namespace(self):
        with mock.patch.dict(os.environ, self.env, clear=False):
            backend = load_backend()
            self.assertEqual(backend.root_path("/tmp/foxair-test"), Path("/tmp/foxair-test"))

    def test_source_explicitly_uses_root_host_shell(self):
        source = BACKEND_PATH.read_text(encoding="utf-8")
        self.assertIn('["/bin/sh", "-c", command]', source)
        self.assertIn("intentionally exposes a root Debian shell", source)


if __name__ == "__main__":
    unittest.main()
