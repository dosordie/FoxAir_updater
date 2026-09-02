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
            "restore_row = self._layout_containing(layout, self.original_restore_btn)",
            self.source,
        )
        self.assertIn(
            "restore_row.indexOf(self.original_restore_btn)",
            self.source,
        )
        self.assertIn("def _original_restore(self):", self.source)
        self.assertIn("super()._original_restore()", self.source)
        self.assertNotIn("layout.removeWidget(self.restore_btn)", self.source)

    def test_technical_runner_log_opens_a_read_only_dialog(self):
        self.assertIn("def _show_runner_log_dialog(self, output: str)", self.source)
        self.assertIn("QPlainTextEdit", self.source)
        self.assertIn('if op == "runner-log":', self.source)
        self.assertIn("self._show_runner_log_dialog(output)", self.source)
        self.assertIn("text.setReadOnly(True)", self.source)


if __name__ == "__main__":
    unittest.main()
