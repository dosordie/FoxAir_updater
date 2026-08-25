import unittest
from pathlib import Path

from updater.common.phnix_statistics_maintenance import (
    MAINBOARD_OTA_OFFSET,
    REMOTE_SERVICE,
    STATISTICS_SIZE,
    MaintenanceError,
    counter_from_bytes,
    patch_counter,
    stable_single_service_snapshot,
)


class FakeSnapshotAdb:
    def __init__(self, pidof_answers):
        self.pidof_answers = iter(pidof_answers)

    def shell(self, command, check=False):
        if command == "pidof phnixIot4G || true":
            return next(self.pidof_answers)
        if command.startswith("readlink /proc/"):
            return REMOTE_SERVICE
        if "TracerPid" in command:
            return "0"
        raise AssertionError(f"unexpected shell command: {command}")


class StatisticsMaintenanceTests(unittest.TestCase):
    def test_counter_patch_changes_only_four_bytes_at_0x24(self):
        original = bytes(range(STATISTICS_SIZE))
        patched = patch_counter(original, 0x12345678)
        self.assertEqual(len(patched), STATISTICS_SIZE)
        self.assertEqual(
            patched[:MAINBOARD_OTA_OFFSET], original[:MAINBOARD_OTA_OFFSET]
        )
        self.assertEqual(
            patched[MAINBOARD_OTA_OFFSET + 4 :],
            original[MAINBOARD_OTA_OFFSET + 4 :],
        )
        self.assertEqual(
            patched[MAINBOARD_OTA_OFFSET : MAINBOARD_OTA_OFFSET + 4],
            b"\x78\x56\x34\x12",
        )
        self.assertEqual(counter_from_bytes(patched), 0x12345678)

    def test_counter_is_uint32_only(self):
        raw = bytes(STATISTICS_SIZE)
        with self.assertRaises(MaintenanceError):
            patch_counter(raw, -1)
        with self.assertRaises(MaintenanceError):
            patch_counter(raw, 0x1_0000_0000)

    def test_wrong_statistics_size_is_rejected(self):
        with self.assertRaises(MaintenanceError):
            patch_counter(bytes(STATISTICS_SIZE - 1), 0)
        with self.assertRaises(MaintenanceError):
            counter_from_bytes(bytes(STATISTICS_SIZE + 1))

    def test_service_snapshot_retries_transient_double_pid(self):
        adb = FakeSnapshotAdb(["5385 5383", "5383", "5383"])
        snapshot = stable_single_service_snapshot(adb, attempts=3, delay=0)
        self.assertTrue(snapshot["stable"])
        self.assertEqual(snapshot["pid"], 5383)
        self.assertEqual(snapshot["pids"], [5383])
        self.assertEqual(snapshot["path"], REMOTE_SERVICE)
        self.assertEqual(snapshot["tracer"], "0")
        self.assertEqual(snapshot["attempts"], 2)

    def test_service_snapshot_rejects_persistent_double_pid(self):
        adb = FakeSnapshotAdb(["5385 5383", "5385 5383", "5385 5383"])
        snapshot = stable_single_service_snapshot(adb, attempts=3, delay=0)
        self.assertFalse(snapshot["stable"])
        self.assertIsNone(snapshot["pid"])
        self.assertEqual(snapshot["pids"], [5385, 5383])

    def test_maintenance_core_is_separate_from_ota_controller(self):
        source = Path(
            "updater/common/phnix_statistics_maintenance.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import phnix_local_ota_controller", source)
        self.assertNotIn("from tools.phnix_ota", source)
        self.assertIn(
            'REMOTE_STATISTICS = "/data/phnixIot_device_statisic"', source
        )
        self.assertIn("MAINBOARD_OTA_OFFSET = 0x24", source)
        self.assertIn("kill -STOP", source)
        self.assertIn("kill -TERM", source)
        self.assertIn("kill -CONT", source)
        self.assertIn("service_singleton", source)
        self.assertIn("service_stable", source)
        self.assertIn("stable_single_service_snapshot", source)
        self.assertIn("SERVICE_SNAPSHOT_ATTEMPTS = 3", source)
        self.assertIn("RESCUE_TIMEOUT_SECONDS = 90", source)
        self.assertIn("arm_watchdog_rescue", source)
        self.assertIn("cp -p {REMOTE_STATISTICS} {REMOTE_STAGE}", source)
        self.assertIn("mv {REMOTE_STAGE} {REMOTE_STATISTICS}", source)
        self.assertNotIn("/dev/ttyHSL2", source)
        self.assertNotIn("FC03", source)
        self.assertNotIn("of=/proc/", source)


if __name__ == "__main__":
    unittest.main()
