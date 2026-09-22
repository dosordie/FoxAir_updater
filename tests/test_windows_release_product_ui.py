import unittest
from pathlib import Path


class WindowsReleaseProductUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("updater/windows/foxair_updater_release_product.py").read_text(
            encoding="utf-8"
        )
        cls.user_source = Path(
            "updater/windows/foxair_updater_runner_user_gui.py"
        ).read_text(encoding="utf-8")

    def test_status_page_is_split_into_three_functional_sections(self):
        self.assertIn("current_box = QGroupBox(", self.user_source)
        self.assertIn("recovery_box = QGroupBox(", self.user_source)
        self.assertIn("finish_box = QGroupBox(", self.user_source)
        self.assertIn("self.abort_summary_label", self.user_source)
        self.assertIn("self.cleanup_summary_label", self.user_source)
        self.assertIn("self.status_finish_layout", self.user_source)

    def test_clean_dtu_checkbox_is_in_advanced_cleanup_section(self):
        self.assertIn("advanced_box = QGroupBox(", self.source)
        self.assertIn(
            "self.status_finish_layout.addWidget(advanced_box)",
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

    def test_manual_ack_cleanup_controls_remain_visible_as_fallback(self):
        self.assertIn("self.runner_ack_btn.setVisible(True)", self.source)
        self.assertIn("self.runner_cleanup_btn.setVisible(True)", self.source)
        self.assertIn("auto_finalize_active = bool(self._auto_finalize_run_id)", self.source)
        self.assertIn("self.runner_ack_btn.setEnabled(False)", self.source)
        self.assertIn("self.runner_cleanup_btn.setEnabled(False)", self.source)
        self.assertIn("self._auto_cleanup_retry_visible", self.source)

    def test_firmware_toolbar_has_lte_dtu_debug_shortcut_left_of_diagnostics(self):
        self.assertIn("self.update_debug_monitor_btn = QPushButton(", self.source)
        self.assertIn(
            "self.update_debug_monitor_btn.clicked.connect(self._open_debug_monitor)",
            self.source,
        )
        self.assertIn(
            "toolbar.insertWidget(insert_at, self.update_debug_monitor_btn)",
            self.source,
        )
        self.assertIn(
            "toolbar.insertWidget(insert_at + 1, self.diagnostics_button)",
            self.source,
        )

    def test_technical_runner_log_opens_a_read_only_dialog(self):
        self.assertIn("def _show_runner_log_dialog(self, output: str)", self.source)
        self.assertIn("QPlainTextEdit", self.source)
        self.assertIn('if op == "runner-log":', self.source)
        self.assertIn("self._show_runner_log_dialog(output)", self.source)
        self.assertIn("text.setReadOnly(True)", self.source)


if __name__ == "__main__":
    unittest.main()
