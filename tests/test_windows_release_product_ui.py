import unittest
from pathlib import Path


class WindowsReleaseProductUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("updater/windows/foxair_updater_release_product.py").read_text(
            encoding="utf-8"
        )

    def test_clean_dtu_checkbox_is_attached_to_original_restore_action(self):
        self.assertIn(
            "restore_parent = self.original_restore_btn.parentWidget()",
            self.source,
        )
        self.assertIn(
            "restore_parent_layout = restore_parent.layout()",
            self.source,
        )
        self.assertIn(
            "restore_row.indexOf(self.original_restore_btn)",
            self.source,
        )
        self.assertIn("def _original_restore(self):", self.source)
        self.assertIn("super()._original_restore()", self.source)
        self.assertNotIn("layout.removeWidget(self.restore_btn)", self.source)

    def test_success_and_same_version_are_auto_archived_then_cleaned(self):
        self.assertIn(
            'AUTO_FINALIZE_RESULTS = {"success", "same-version"}',
            self.source,
        )
        self.assertIn("def _schedule_terminal_auto_finalize", self.source)
        self.assertIn("def _start_terminal_auto_archive", self.source)
        self.assertIn('self._run("runner-auto-diagnostics"', self.source)
        self.assertIn(
            'self._run_runner("runner-auto-ack", "ack", "--run-id", run_id)',
            self.source,
        )
        self.assertIn(
            'self._run_runner("runner-auto-cleanup", "cleanup", "--run-id", run_id)',
            self.source,
        )
        self.assertIn("archive.is_file()", self.source)

    def test_manual_ack_cleanup_controls_are_hidden_in_normal_flow(self):
        self.assertIn("self.runner_ack_btn.setVisible(False)", self.source)
        self.assertIn("self.runner_cleanup_btn.setVisible(False)", self.source)
        self.assertIn("self._auto_cleanup_retry_visible", self.source)
        self.assertIn("Gespeicherte Updatedaten erneut löschen", self.source)

    def test_technical_runner_log_opens_a_read_only_dialog(self):
        self.assertIn("def _show_runner_log_dialog(self, output: str)", self.source)
        self.assertIn("QPlainTextEdit", self.source)
        self.assertIn('if op == "runner-log":', self.source)
        self.assertIn("self._show_runner_log_dialog(output)", self.source)
        self.assertIn("text.setReadOnly(True)", self.source)


if __name__ == "__main__":
    unittest.main()
