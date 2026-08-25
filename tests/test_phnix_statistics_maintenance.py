import unittest
from pathlib import Path
from unittest.mock import patch

import updater.common.phnix_statistics_maintenance as maintenance
from updater.common.phnix_statistics_maintenance import (
    MAINBOARD_OTA_OFFSET,
    REMOTE_SERVICE,
    STATISTICS_SIZE,
    MaintenanceError,
    counter_from_bytes,
    patch_counter,
    stable_single_service_snapshot,
    stop_service_for_maintenance,
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


class FakeStopAdb:
    def __init__(self, pid=5383):
        self.pid = pid
        self.alive = True
        self.commands = []

    def shell(self, command, check=False):
        self.commands.append(command)
        if command == "pidof phnixIot4G || true":
            return str(self.pid) if self.alive else ""
        if command == f"kill -TERM {self.pid}":
            # Mirrors the live modem observation: TERM does not make the
            # service disappear within the maintenance grace period.
            return ""
        if command == f"kill -KILL {self.pid}":
            self.alive = False
            return ""
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

    def test_service_stop_escalates_from_term_to_kill_like_ota_restore(self):
        adb = FakeStopAdb()
        with patch.object(maintenance, "SERVICE_TERM_GRACE_SECONDS", 0.01), patch.object(
            maintenance, "SERVICE_KILL_TIMEOUT_SECONDS", 0.05
        ):
            method = stop_service_for_maintenance(adb, 5383)
        self.assertEqual(method, "kill")
        self.assertIn("kill -TERM 5383", adb.commands)
        self.assertIn("kill -KILL 5383", adb.commands)
        self.assertFalse(adb.alive)

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
        self.assertIn("kill -KILL", source)
        self.assertIn("kill -CONT", source)
        self.assertIn("stop_service_for_maintenance", source)
        self.assertIn("SERVICE_TERM_GRACE_SECONDS = 2.0", source)
        self.assertIn("SERVICE_KILL_TIMEOUT_SECONDS = 4.0", source)
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
