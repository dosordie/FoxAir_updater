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
        self.device_tmp = self.state / "device-tmp"
        self.fake_bwrap = self.root / "bwrap"
        self.fake_bwrap.write_text("#!/bin/sh\n", encoding="utf-8")
        self.env = {
            "FOXAIR_QEMU_LAB_ROOT": str(self.lab),
            "FOXAIR_QEMU_LAB_ROOTFS": str(self.rootfs),
            "FOXAIR_FAKE_ADB_STATE": str(self.state),
            "FOXAIR_FAKE_ADB_TMP": str(self.device_tmp),
            "FOXAIR_FAKE_ADB_BWRAP": str(self.fake_bwrap),
            "FOXAIR_QEMU_FAKE_PID": "4100",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_phnix_pid_still_uses_virtual_process_view(self):
        with mock.patch.dict(os.environ, self.env, clear=False):
            backend = load_backend()
            self.assertEqual(backend.shell("pidof phnixIot4G || true"), (0, b"4100\n"))

    def test_tmp_sync_path_is_dedicated_not_host_tmp(self):
        with mock.patch.dict(os.environ, self.env, clear=False):
            backend = load_backend()
            self.assertEqual(backend.root_path("/tmp"), self.device_tmp)
            self.assertEqual(backend.root_path("/tmp/foxair-test"), self.device_tmp / "foxair-test")
            self.assertNotEqual(backend.root_path("/tmp/foxair-test"), Path("/tmp/foxair-test"))

    def test_data_and_cache_sync_paths_map_to_qemu_rootfs(self):
        with mock.patch.dict(os.environ, self.env, clear=False):
            backend = load_backend()
            rootfs = self.rootfs.resolve()
            self.assertEqual(backend.root_path("/data/phnixIot4G"), rootfs / "data/phnixIot4G")
            self.assertEqual(backend.root_path("/cache/test.bin"), rootfs / "cache/test.bin")

    def test_shell_namespace_creates_mount_targets_before_binding(self):
        with mock.patch.dict(os.environ, self.env, clear=False):
            backend = load_backend()
            argv = backend._sandbox_command("printf ok")

        data_source = str(self.rootfs.resolve() / "data")
        cache_source = str(self.rootfs.resolve() / "cache")
        self.assertIn(data_source, argv)
        self.assertIn(cache_source, argv)
        self.assertIn(str(self.device_tmp), argv)

        data_dir = argv.index("/data", argv.index("--dir"))
        cache_dir = argv.index("/cache", data_dir + 1)
        data_bind = argv.index(data_source)
        cache_bind = argv.index(cache_source)
        self.assertLess(data_dir, data_bind)
        self.assertLess(cache_dir, cache_bind)
        self.assertEqual(argv[-3:], ["/bin/sh", "-c", "printf ok"])

    def test_source_documents_no_global_host_remapping(self):
        source = BACKEND_PATH.read_text(encoding="utf-8")
        self.assertIn("normal Debian /data, /cache and /tmp separate", source)
        self.assertIn('"--dir", "/data"', source)
        self.assertIn('"--dir", "/cache"', source)
        self.assertIn('"--bind", str(tmp), "/tmp"', source)

    def test_installer_removes_only_legacy_global_links(self):
        source = Path("tools/testvm/fake_adb/install.sh").read_text(encoding="utf-8")
        self.assertIn("bubblewrap", source)
        self.assertIn("FOXAIR_FAKE_ADB_TMP=$DEVICE_TMP", source)
        self.assertIn('remove_legacy_link /data "$ROOTFS/data"', source)
        self.assertIn('remove_legacy_link /cache "$ROOTFS/cache"', source)
        self.assertNotIn("link_rootfs_dir data", source)
        self.assertNotIn("link_rootfs_dir cache", source)
        self.assertIn("Debian-Pfade:  /data, /cache und /tmp werden nicht umgebogen", source)


if __name__ == "__main__":
    unittest.main()
