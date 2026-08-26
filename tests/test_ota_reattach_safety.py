import unittest
from pathlib import Path


class OtaReattachSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.controller = Path("tools/phnix_ota/phnix_local_ota_controller.py").read_text(
            encoding="utf-8"
        )

    def test_pre_c5a8_exception_still_requests_guarded_hold(self):
        self.assertIn("if not safe_terminal and not transfer_started:", self.controller)
        self.assertIn('REMOTE_HELPER} hold --status {REMOTE_STATUS}', self.controller)

    def test_post_c5a8_monitoring_loss_does_not_hold_restore_or_cancel(self):
        run_update = self.controller.split("def run_update", 1)[1].split("def cancel_update", 1)[0]
        exception_path = run_update.rsplit("except BaseException:", 1)[1].split("finally:", 1)[0]
        post_c5a8 = exception_path.split("elif not safe_terminal:", 1)[1]
        self.assertIn('"monitoring-connection-lost"', post_c5a8)
        for forbidden in (" hold ", "restore", "C36A", "cancel_update"):
            self.assertNotIn(forbidden, post_c5a8)

    def test_status_exposes_read_only_reattach_fields(self):
        status = self.controller.split("def remote_status", 1)[1].split("def ", 1)[0]
        for field in ("run_active", "transfer_started", "service_pid", "debugger_pids", "ota_info"):
            self.assertIn(field, status)
        for forbidden in ("rm -", "kill ", "mv ", "push(", "write_file"):
            self.assertNotIn(forbidden, status)


if __name__ == "__main__":
    unittest.main()
