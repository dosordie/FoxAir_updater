import unittest
from pathlib import Path
from unittest.mock import patch

from updater.common.phnix_service_restart import RESTART_MARKERS, restart_phnix_iot_service


class FakeAdb:
    def __init__(self, marker=None, pids=("123", "456")):
        self.marker = marker
        self.pids = iter(pids)
        self.commands = []

    def shell(self, command, check=True):
        self.commands.append(command)
        if command.startswith("if [ -e"):
            return "PRESENT" if self.marker and self.marker in command else "ABSENT"
        if command == "pidof phnixIot4G":
            return next(self.pids, "")
        return ""


class WindowsServiceRestartTests(unittest.TestCase):
    def test_each_ota_marker_prevents_kill(self):
        for marker in RESTART_MARKERS:
            with self.subTest(marker=marker):
                adb = FakeAdb(marker=marker)
                with self.assertRaisesRegex(RuntimeError, "Firmwareupdates"):
                    restart_phnix_iot_service(adb)
                self.assertFalse(any("kill" in command for command in adb.commands))

    @patch("updater.common.phnix_service_restart.time.sleep", return_value=None)
    def test_sigterm_and_new_pid_report_success(self, _sleep):
        adb = FakeAdb()
        result = restart_phnix_iot_service(adb, timeout=1)
        self.assertIn("kill -TERM 123", adb.commands)
        self.assertNotIn("kill -9", " ".join(adb.commands))
        self.assertIn("Alte PID: 123", result)
        self.assertIn("Neue PID: 456", result)

    @patch("updater.common.phnix_service_restart.time.sleep", return_value=None)
    @patch("updater.common.phnix_service_restart.time.monotonic", side_effect=(0, 0, 2))
    def test_timeout_has_no_sigkill_fallback(self, _monotonic, _sleep):
        adb = FakeAdb(pids=("123", "123"))
        with self.assertRaisesRegex(RuntimeError, "nicht bestätigt"):
            restart_phnix_iot_service(adb, timeout=1)
        self.assertNotIn("kill -9", " ".join(adb.commands))

    def test_ui_has_default_no_and_busy_button_guard(self):
        source = Path("updater/windows/foxair_updater_maintenance.py").read_text(encoding="utf-8")
        self.assertIn("QMessageBox.No,", source)
        self.assertIn("self.phnix_restart_btn.setEnabled(not self.busy", source)
        self.assertIn("env=self._process_env()", source)


if __name__ == "__main__":
    unittest.main()
