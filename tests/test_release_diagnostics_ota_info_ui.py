from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "updater/windows/foxair_updater_release_product.py"


class ReleaseDiagnosticsOtaInfoUiTests(unittest.TestCase):
    def test_release_ui_uses_shared_diagnostics_bundle_path(self):
        source = SOURCE.read_text(encoding="utf-8")
        method = source.split("def _save_diagnostic_bundle", 1)[1].split(
            "def _schedule_terminal_auto_finalize", 1
        )[0]
        self.assertIn("self._diagnostics_core_path()", method)
        self.assertIn('"--output"', method)
        self.assertIn('"--host-log"', method)
        self.assertIn('self._run("runner-diagnostics"', method)


if __name__ == "__main__":
    unittest.main()
