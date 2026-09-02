import json
import unittest

from updater.dtu_ota.cleanup import CLEAN_PATHS, clean, safety_snapshot, CleanupError


class FakeAdb:
    def __init__(self, *, files=None, ps=""):
        self.files = dict(files or {})
        self.ps = ps
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


if __name__ == "__main__":
    unittest.main()
