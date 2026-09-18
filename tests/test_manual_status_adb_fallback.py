import unittest
from pathlib import Path


class ManualStatusAdbFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path(
            "updater/windows/foxair_updater_runner_enduser.py"
        ).read_text(encoding="utf-8")

    def test_manual_status_reads_current_before_reconnect(self):
        method = self.ui.split("def _reattach_ota", 1)[1].split(
            "def _runner_current_transport_error", 1
        )[0]
        self.assertIn('self._run_runner("runner-current", "current")', method)
        self.assertNotIn('"reconnect"', method)

    def test_reconnect_is_limited_to_adb_transport_errors(self):
        helper = self.ui.split("def _runner_current_transport_error", 1)[1].split(
            "def _poll_runner_status", 1
        )[0]
        self.assertIn('lower.startswith("adb ")', helper)
        self.assertIn("no devices/emulators found", helper)
        self.assertIn("device offline", helper)
        self.assertIn("connection refused", helper)

    def test_retry_waits_for_confirmed_device_and_runs_only_once(self):
        done = self.ui.split("def _done(self, op, code, output):", 1)[1].split(
            "\ndef main():", 1
        )[0]
        self.assertIn('self._run("reconnect", [str(adb), "reconnect"])', done)
        self.assertIn('"\\tdevice" in line or " device " in line', done)
        self.assertIn('self._run_runner("runner-current", "current")', done)
        self.assertIn("self._manual_status_direct_attempt = False", done)


if __name__ == "__main__":
    unittest.main()
