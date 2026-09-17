from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "updater/windows/foxair_updater_release_product.py"


class ReleaseDiagnosticsOtaInfoUiTests(unittest.TestCase):
    def test_release_ui_mentions_ota_info_is_included(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("originale PHNIX-OTA_INFO als ZIP", text)
        self.assertIn("Die originale PHNIX-OTA_INFO wurde eingebunden", text)
        self.assertNotIn("Firmware, OTA_INFO und Statistik-Binärdaten wurden nicht eingebunden", text)


if __name__ == "__main__":
    unittest.main()
