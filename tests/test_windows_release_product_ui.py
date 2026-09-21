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
            "restore_row = self._layout_containing(",
            self.source,
        )
        self.assertIn(
            "restore_row.indexOf(self.original_restore_btn)",
            self.source,
        )
        self.assertIn(
            "restore_row.insertWidget(insert_at + 1, self.clean_dtu_after_restore)",
            self.source,
        )
        self.assertIn(
            "restore_parent_layout.insertWidget(status_index, self.full_cleanup_note)",
            self.source,
        )
        self.assertIn("def _original_restore(self):", self.source)
        self.assertIn("super()._original_restore()", self.source)
        self.assertNotIn("layout.removeWidget(self.restore_btn)", self.source)

    def test_cleanup_modes_are_explained_as_different_actions(self):
        self.assertIn(
            "Danach FoxAir-Updater-Dateien vollständig vom LTE-Modem entfernen",
            self.source,
        )
        self.assertIn("Normalerweise nicht erforderlich:", self.source)
        self.assertIn(
            "Sie stellt zuerst den normalen PHNIX-Betrieb kontrolliert",
            self.source,
        )
        self.assertIn(
            "wieder her und entfernt anschließend alle bekannten FoxAir-Updater-Arbeitsdateien.",
            self.source,
        )
        self.assertIn("Automatisches Aufräumen nach Firmwareupdate:", self.source)
        self.assertIn("Update-Protokolle lokal sichern", self.source)
        self.assertIn("abgeschlossenes Ergebnis bestätigen", self.source)
        self.assertIn("gespeicherte Laufdaten entfernen", self.source)
        self.assertIn(
            "Der normale PHNIX-Betrieb wird dabei nicht erneut verändert.",
            self.source,
        )

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
        self.assertIn("Manueller Fallback:", self.source)
        self.assertIn("auto_finalize_active = bool(self._auto_finalize_run_id)", self.source)
        self.assertIn("self.runner_ack_btn.setEnabled(False)", self.source)
        self.assertIn("self.runner_cleanup_btn.setEnabled(False)", self.source)
        self.assertIn("self._auto_cleanup_retry_visible", self.source)
        self.assertIn("Gespeicherte Updatedaten erneut löschen", self.source)

    def test_firmware_toolbar_has_lte_dtu_debug_shortcut_left_of_diagnostics(self):
        self.assertIn(
            'self.update_debug_monitor_btn = QPushButton("LTE DTU Debug öffnen")',
            self.source,
        )
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
        self.assertIn("denselben read-only PHNIX-Debugmonitor", self.source)

    def test_technical_runner_log_opens_a_read_only_dialog(self):
        self.assertIn("def _show_runner_log_dialog(self, output: str)", self.source)
        self.assertIn("QPlainTextEdit", self.source)
        self.assertIn('if op == "runner-log":', self.source)
        self.assertIn("self._show_runner_log_dialog(output)", self.source)
        self.assertIn("text.setReadOnly(True)", self.source)


if __name__ == "__main__":
    unittest.main()
