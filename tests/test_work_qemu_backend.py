import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


BACKEND_PATH = Path("tools/testvm/fake_adb/qemu_work_lab_backend.py")


def load_backend():
    spec = importlib.util.spec_from_file_location("foxair_work_qemu_backend_tested", BACKEND_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class WorkQemuBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lab = self.root / "phnix-lab"
        self.rootfs = self.lab / "rootfs"
        for directory in ("data", "cache", "tmp", "usr/bin"):
            (self.rootfs / directory).mkdir(parents=True, exist_ok=True)
        (self.rootfs / "data/phnixIot4G").write_bytes(b"ORIGINAL")
        (self.rootfs / "usr/bin/qemu-arm-static").write_bytes(b"qemu")
        self.state = self.root / "state"
        self.env = {
            "FOXAIR_QEMU_LAB_ROOT": str(self.lab),
            "FOXAIR_QEMU_LAB_ROOTFS": str(self.rootfs),
            "FOXAIR_FAKE_ADB_STATE": str(self.state),
            "FOXAIR_QEMU_FAKE_PID": "4100",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_df_is_host_side_and_points_at_real_qemu_data_dir(self):
        with mock.patch.dict(os.environ, self.env, clear=False):
            backend = load_backend()
            code, output = backend.shell("df -k /data 2>/dev/null")
        self.assertEqual(code, 0)
        self.assertIn(b"Filesystem", output)
        self.assertNotIn(b"QEMU-/bin/sh", output)

    def test_status_listener_probe_does_not_require_rootfs_shell(self):
        with mock.patch.dict(os.environ, self.env, clear=False):
            backend = load_backend()
            code, output = backend.shell("netstat -lnt 2>/dev/null | awk '$4 ~ /:8081$/ {print}'")
        self.assertEqual(code, 0)
        self.assertIsInstance(output, bytes)

    def test_real_rs485_fault_mapping_is_exact(self):
        with mock.patch.dict(os.environ, self.env, clear=False):
            backend = load_backend()
            success, _ = backend._scenario_to_lab_env("scenario", "success")
            same, _ = backend._scenario_to_lab_env("scenario", "same-version")
            stall350, _ = backend._scenario_to_lab_env("scenario", "stall-c350")
            stall5a8, _ = backend._scenario_to_lab_env("scenario", "stall-c5a8")
            unsupported = backend._scenario_to_lab_env("scenario", "crc-error")
        self.assertEqual(success["FAULT_SCENARIO"], "success")
        self.assertEqual(same["FAULT_SCENARIO"], "c350-status0")
        self.assertEqual(stall350["FAULT_SCENARIO"], "no-c350-status")
        self.assertEqual(stall5a8["FAULT_SCENARIO"], "no-block-ack")
        self.assertIsNone(unsupported)

    def test_backend_never_uses_arm_rootfs_shell(self):
        source = BACKEND_PATH.read_text(encoding="utf-8")
        self.assertNotIn("/bin/sh im PHNIX-Lab", source)
        self.assertIn("run_scenario_lab.sh", source)
        self.assertIn("rs485_fault_emulator.py", source)
        self.assertIn("LOCAL_OTA_FULL_TRANSFER", source)


if __name__ == "__main__":
    unittest.main()
