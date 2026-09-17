import json
import unittest

from updater.dtu_ota.cleanup import safety_snapshot


class FakeAdb:
    def __init__(
        self,
        run_id: str,
        *,
        offset: int,
        length: int,
        saved_boot: str = "boot-before-power-cycle",
        current_boot: str = "boot-after-power-cycle",
    ):
        self.run_id = run_id
        self.current_boot = current_boot
        raw = bytearray(b"\0" * 220)
        raw[212:216] = offset.to_bytes(4, "little")
        raw[216:220] = length.to_bytes(4, "little")
        self.ota_info = bytes(raw)
        self.files = {
            "/data/foxair_ota_runner/active.lock/run_id": run_id,
            f"/data/foxair_ota_runner/runs/{run_id}/status.json": json.dumps(
                {
                    "schema": "foxair-dtu-ota-run-v1",
                    "run_id": run_id,
                    "terminal": False,
                    "phase": "original-service-active-unmonitored",
                    "reason": "hook_monitor_lost",
                    "boot_id": saved_boot,
                }
            ),
            "/data/foxair_ota_runner": "dir",
        }

    def shell(self, command, check=True):
        if command.startswith("cat '"):
            path = command.split("'", 2)[1]
            return self.files.get(path, "")
        if command.startswith("cat /proc/sys/kernel/random/boot_id"):
            return self.current_boot
        if command.startswith("awk '/^btime /"):
            return ""
        if command.startswith("awk '{print \"pid1-"):
            return ""
        if command.startswith("test -e '"):
            path = command.split("'", 2)[1]
            return "1" if path in self.files else ""
        if command.startswith("ps 2>/dev/null"):
            return ""
        raise AssertionError(command)

    def read_file(self, path):
        if path == "/data/phnixIot_device_OTA_INFO":
            return self.ota_info
        raise AssertionError(path)


class CompletedOtaInfoCleanupTests(unittest.TestCase):
    def test_previous_boot_runner_with_complete_transfer_counters_is_cleanable(self):
        run_id = "20260914-173921-0700"
        adb = FakeAdb(run_id, offset=287598, length=287598)

        snapshot = safety_snapshot(adb)

        self.assertTrue(snapshot["safe"])
        self.assertEqual(snapshot["ota_info"]["offset"], 287598)
        self.assertEqual(snapshot["ota_info"]["length"], 287598)
        self.assertTrue(any("vollständig übertragenen" in note for note in snapshot["notes"]))
        self.assertTrue(any("vorherigem DTU-Boot" in note for note in snapshot["notes"]))

    def test_same_boot_runner_with_complete_transfer_counters_is_cleanable_when_helpers_are_gone(self):
        run_id = "20260914-173921-0703"
        adb = FakeAdb(
            run_id,
            offset=287598,
            length=287598,
            saved_boot="same-boot",
            current_boot="same-boot",
        )

        snapshot = safety_snapshot(adb)

        self.assertTrue(snapshot["safe"])
        self.assertTrue(any("aktuellen DTU-Boot" in note for note in snapshot["notes"]))
        self.assertTrue(any("vollständig übertragenen" in note for note in snapshot["notes"]))

    def test_previous_boot_runner_with_partial_transfer_stays_blocked(self):
        run_id = "20260914-173921-0701"
        adb = FakeAdb(run_id, offset=120000, length=287598)

        snapshot = safety_snapshot(adb)

        self.assertFalse(snapshot["safe"])
        self.assertTrue(any("fortsetzbaren OTA-Zustand" in blocker for blocker in snapshot["blockers"]))

    def test_same_boot_runner_with_partial_transfer_stays_blocked(self):
        run_id = "20260914-173921-0704"
        adb = FakeAdb(
            run_id,
            offset=120000,
            length=287598,
            saved_boot="same-boot",
            current_boot="same-boot",
        )

        snapshot = safety_snapshot(adb)

        self.assertFalse(snapshot["safe"])
        self.assertTrue(any("fortsetzbaren OTA-Zustand" in blocker for blocker in snapshot["blockers"]))


if __name__ == "__main__":
    unittest.main()
