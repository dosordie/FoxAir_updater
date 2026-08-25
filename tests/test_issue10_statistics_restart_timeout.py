import unittest
from pathlib import Path


class Issue10StatisticsRestartTimeoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(
            "updater/common/phnix_statistics_maintenance.py"
        ).read_text(encoding="utf-8")

    def test_service_restart_wait_has_margin_above_observed_23_seconds(self):
        self.assertIn(
            "def wait_service_restored(adb: AdbClient, old_pid: int, timeout: float = 40.0)",
            self.source,
        )

    def test_watchdog_rescue_timeout_is_unchanged(self):
        self.assertIn("RESCUE_TIMEOUT_SECONDS = 90", self.source)


if __name__ == "__main__":
    unittest.main()
