import json
import unittest

from updater.dtu_ota.cleanup import CLEAN_PATHS, clean, safety_snapshot, CleanupError


IDLE_OTA_INFO = b"\0" * 220


class FakeAdb:
    def __init__(self, *, files=None, ps="", ota_info=IDLE_OTA_INFO):
        self.files = dict(files or {})
        self.ps = ps
        self.ota_info = ota_info
        self.removed = []

    def shell(self, command, check=True):
        if command.startswith("cat '"):
            path = command.split("'", 2)[1]
            return self.files.get(path, "")
        if command.startswith("test -e '"):
            path = command.split("'", 2)[1]
            return "1" if path in self.files else ""
        if command.startswith("ps 2>/dev/null"):
            return self.ps
        if command.startswith("rm -rf '"):
            path = command.split("'", 2)[1]
            self.removed.append(path)
            for key in list(self.files):
                if key == path or key.startswith(path.rstrip("/") + "/"):
                    del self.files[key]
            return ""
        raise AssertionError(command)

    def read_file(self, path):
        if path == "/data/phnixIot_device_OTA_INFO":
            return self.ota_info
        raise AssertionError(path)


class DtuCleanupTests(unittest.TestCase):
    def test_clean_paths_never_include_original_phnix_state(self):
        forbidden = {
            "/data/phnixIot4G",
            "/cache/phnixIot_device_OTA",
            "/data/phnixIot_device_OTA_INFO",
            "/data/phnixIot_device_statisic",
        }
        self.assertTrue(forbidden.isdisjoint(CLEAN_PATHS))

    def test_active_nonterminal_runner_blocks_cleanup(self):
        run_id = "20260902-150000-0001"
        adb = FakeAdb(
            files={
                "/data/foxair_ota_runner/active.lock/run_id": run_id,
                f"/data/foxair_ota_runner/runs/{run_id}/status.json": json.dumps(
                    {
                        "schema": "foxair-dtu-ota-run-v1",
                        "run_id": run_id,
                        "terminal": False,
                        "phase": "c5a8",
                    }
                ),
                "/data/foxair_ota_runner": "dir",
            }
        )
        snapshot = safety_snapshot(adb)
        self.assertFalse(snapshot["safe"])
        with self.assertRaises(CleanupError):
            clean(adb)
        self.assertEqual(adb.removed, [])

    def test_terminal_stale_runner_lock_can_be_removed(self):
        run_id = "20260902-150000-0002"
        adb = FakeAdb(
            files={
                "/data/foxair_ota_runner/active.lock/run_id": run_id,
                f"/data/foxair_ota_runner/runs/{run_id}/status.json": json.dumps(
                    {
                        "schema": "foxair-dtu-ota-run-v1",
                        "run_id": run_id,
                        "terminal": True,
                        "phase": "same-version",
                    }
                ),
                "/data/foxair_ota_runner": "dir",
                "/tmp/phnix_ota_status.json": "{}",
            }
        )
        result = clean(adb)
        self.assertTrue(result["ok"])
        self.assertEqual(result["remaining"], [])
        self.assertIn("/data/foxair_ota_runner", adb.removed)

    def test_legacy_transfer_marker_blocks_even_without_helper_process(self):
        adb = FakeAdb(
            files={
                "/tmp/phnix_ota_hook/transfer-started": "1",
                "/tmp/phnix_ota_hook": "dir",
            }
        )
        snapshot = safety_snapshot(adb)
        self.assertFalse(snapshot["safe"])
        self.assertTrue(any("Firmwareübertragung" in item for item in snapshot["blockers"]))

    def test_stale_legacy_run_active_without_process_is_cleanable(self):
        adb = FakeAdb(
            files={
                "/tmp/phnix_ota_hook/run.active": "1",
                "/tmp/phnix_ota_hook": "dir",
                "/data/phnix_local_ota": "dir",
            }
        )
        snapshot = safety_snapshot(adb)
        self.assertTrue(snapshot["safe"])
        result = clean(adb)
        self.assertTrue(result["ok"])

    def test_orphaned_ota_helper_process_blocks_without_any_marker(self):
        adb = FakeAdb(ps="123 root /system/bin/sh /data/foxair_ota_runner/runs/x/payload/dtu_ota_supervisor.sh run x")
        snapshot = safety_snapshot(adb)
        self.assertFalse(snapshot["safe"])
        self.assertTrue(any("Hilfsprozesse" in item for item in snapshot["blockers"]))
        with self.assertRaises(CleanupError):
            clean(adb)
        self.assertEqual(adb.removed, [])

    def test_active_ota_info_resume_state_blocks_cleanup(self):
        raw = bytearray(IDLE_OTA_INFO)
        raw[212:216] = (4096).to_bytes(4, "little")
        raw[216:220] = (289806).to_bytes(4, "little")
        adb = FakeAdb(ota_info=bytes(raw))
        snapshot = safety_snapshot(adb)
        self.assertFalse(snapshot["safe"])
        self.assertEqual(snapshot["ota_info"]["offset"], 4096)
        self.assertEqual(snapshot["ota_info"]["length"], 289806)

    def test_unknown_ota_info_shape_blocks_cleanup(self):
        adb = FakeAdb(ota_info=b"broken")
        snapshot = safety_snapshot(adb)
        self.assertFalse(snapshot["safe"])
        self.assertTrue(any("220 Byte" in item for item in snapshot["blockers"]))


if __name__ == "__main__":
    unittest.main()
