import json
import unittest

from updater.dtu_ota.cleanup import CLEAN_PATHS, clean, safety_snapshot, CleanupError


IDLE_OTA_INFO = b"\0" * 220


class FakeAdb:
    def __init__(self, *, files=None, ps="", ota_info=IDLE_OTA_INFO, boot_id="boot-current"):
        self.files = dict(files or {})
        self.ps = ps
        self.ota_info = ota_info
        self.boot_id = boot_id
        self.removed = []
        self.ps_commands = []

    def shell(self, command, check=True):
        if command.startswith("cat '"):
            path = command.split("'", 2)[1]
            return self.files.get(path, "")
        if command.startswith("cat /proc/sys/kernel/random/boot_id"):
            return self.boot_id
        if command.startswith("awk '/^btime /"):
            return ""
        if command.startswith("awk '{print \"pid1-"):
            return ""
        if command.startswith("test -e '"):
            path = command.split("'", 2)[1]
            return "1" if path in self.files else ""
        if command.startswith("ps 2>/dev/null"):
            self.ps_commands.append(command)
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

    def test_live_nonterminal_runner_process_blocks_cleanup(self):
        run_id = "20260902-150000-0001"
        adb = FakeAdb(
            ps=(
                "4534 root /system/bin/sh "
                f"/data/foxair_ota_runner/runs/{run_id}/payload/dtu_ota_supervisor.sh run {run_id}"
            ),
            files={
                "/data/foxair_ota_runner/active.lock/run_id": run_id,
                f"/data/foxair_ota_runner/runs/{run_id}/status.json": json.dumps(
                    {
                        "schema": "foxair-dtu-ota-run-v1",
                        "run_id": run_id,
                        "terminal": False,
                        "phase": "c5a8",
                        "boot_id": "boot-current",
                    }
                ),
                "/data/foxair_ota_runner": "dir",
            },
        )
        snapshot = safety_snapshot(adb)
        self.assertFalse(snapshot["safe"])
        self.assertTrue(any("Hilfsprozesse" in item for item in snapshot["blockers"]))
        with self.assertRaises(CleanupError):
            clean(adb)
        self.assertEqual(adb.removed, [])

    def test_same_boot_nonterminal_lock_is_cleanable_when_runtime_is_idle(self):
        run_id = "20260914-173921-0600"
        adb = FakeAdb(
            boot_id="boot-current",
            files={
                "/data/foxair_ota_runner/active.lock/run_id": run_id,
                f"/data/foxair_ota_runner/runs/{run_id}/status.json": json.dumps(
                    {
                        "schema": "foxair-dtu-ota-run-v1",
                        "run_id": run_id,
                        "terminal": False,
                        "phase": "original-service-active-unmonitored",
                        "reason": "hook_monitor_lost",
                        "boot_id": "boot-current",
                    }
                ),
                "/data/foxair_ota_runner": "dir",
            },
        )
        snapshot = safety_snapshot(adb)
        self.assertTrue(snapshot["safe"])
        self.assertTrue(any("aktuellen DTU-Boot" in item for item in snapshot["notes"]))
        result = clean(adb)
        self.assertTrue(result["ok"])

    def test_nonterminal_runner_from_previous_boot_can_be_removed_when_everything_else_is_idle(self):
        run_id = "20260914-173921-0700"
        adb = FakeAdb(
            boot_id="boot-after-power-cycle",
            files={
                "/data/foxair_ota_runner/active.lock/run_id": run_id,
                f"/data/foxair_ota_runner/runs/{run_id}/status.json": json.dumps(
                    {
                        "schema": "foxair-dtu-ota-run-v1",
                        "run_id": run_id,
                        "terminal": False,
                        "phase": "original-service-active-unmonitored",
                        "reason": "hook_monitor_lost",
                        "boot_id": "boot-before-power-cycle",
                    }
                ),
                "/data/foxair_ota_runner": "dir",
            },
        )
        snapshot = safety_snapshot(adb)
        self.assertTrue(snapshot["safe"])
        self.assertEqual(snapshot["current_boot_id"], "boot-after-power-cycle")
        self.assertTrue(any("vorherigem DTU-Boot" in item for item in snapshot["notes"]))
        result = clean(adb)
        self.assertTrue(result["ok"])
        self.assertIn("/data/foxair_ota_runner", adb.removed)

    def test_nonterminal_runner_without_saved_boot_proof_is_cleanable_when_runtime_is_idle(self):
        run_id = "20260914-173921-0701"
        adb = FakeAdb(
            files={
                "/data/foxair_ota_runner/active.lock/run_id": run_id,
                f"/data/foxair_ota_runner/runs/{run_id}/status.json": json.dumps(
                    {
                        "schema": "foxair-dtu-ota-run-v1",
                        "run_id": run_id,
                        "terminal": False,
                        "phase": "original-service-active-unmonitored",
                    }
                ),
                "/data/foxair_ota_runner": "dir",
            }
        )
        snapshot = safety_snapshot(adb)
        self.assertTrue(snapshot["safe"])
        self.assertTrue(any("ohne eindeutigen Bootnachweis" in item for item in snapshot["notes"]))

    def test_previous_boot_lock_still_blocks_when_ota_info_is_resumable(self):
        run_id = "20260914-173921-0702"
        raw = bytearray(IDLE_OTA_INFO)
        raw[212:216] = (4096).to_bytes(4, "little")
        raw[216:220] = (289806).to_bytes(4, "little")
        adb = FakeAdb(
            boot_id="boot-new",
            ota_info=bytes(raw),
            files={
                "/data/foxair_ota_runner/active.lock/run_id": run_id,
                f"/data/foxair_ota_runner/runs/{run_id}/status.json": json.dumps(
                    {
                        "schema": "foxair-dtu-ota-run-v1",
                        "run_id": run_id,
                        "terminal": False,
                        "phase": "original-service-active-unmonitored",
                        "boot_id": "boot-old",
                    }
                ),
                "/data/foxair_ota_runner": "dir",
            },
        )
        snapshot = safety_snapshot(adb)
        self.assertFalse(snapshot["safe"])
        self.assertTrue(any("fortsetzbaren OTA-Zustand" in item for item in snapshot["blockers"]))

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

    def test_process_probe_does_not_put_match_terms_in_remote_command(self):
        adb = FakeAdb(ps="14232 root 0:00 /system/bin/sh -c ps 2>/dev/null || true")
        snapshot = safety_snapshot(adb)
        self.assertTrue(snapshot["safe"])
        self.assertEqual(snapshot["ota_helper_processes"], [])
        self.assertEqual(adb.ps_commands, ["ps 2>/dev/null || true"])
        self.assertNotIn("grep", adb.ps_commands[0])
        self.assertNotIn("runtime_hook", adb.ps_commands[0])

    def test_gdb_process_is_still_detected_after_host_side_filtering(self):
        adb = FakeAdb(ps="777 root 0:00 /data/local/tmp/gdbserver :1234 /data/phnixIot4G")
        snapshot = safety_snapshot(adb)
        self.assertFalse(snapshot["safe"])
        self.assertEqual(len(snapshot["ota_helper_processes"]), 1)

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
