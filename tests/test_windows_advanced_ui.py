import unittest
from pathlib import Path


class WindowsAdvancedUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("updater/windows/foxair_updater_app.py").read_text(encoding="utf-8")

    def test_original_service_is_selected_by_default(self):
        self.assertIn("self.backup_service.setChecked(True)", self.source)

    def test_backup_reports_missing_files_and_continues(self):
        self.assertIn('"event": "backup-missing"', self.source)
        self.assertIn('"event": "backup-summary"', self.source)
        self.assertIn("Nicht auf dem LTE-Modem vorhanden:", self.source)
        self.assertIn("Backup abgeschlossen mit Hinweis", self.source)

    def test_manual_cache_copy_is_staged_verified_and_promoted(self):
        self.assertIn('REMOTE_CACHE_FIRMWARE = "/cache/phnixIot_device_OTA"', self.source)
        self.assertIn('REMOTE_CACHE_STAGE = "/cache/.phnixIot_device_OTA.manual-upload"', self.source)
        self.assertIn("sha256sum '{REMOTE_CACHE_STAGE}'", self.source)
        self.assertIn("mv '{REMOTE_CACHE_STAGE}' '{REMOTE_CACHE_FIRMWARE}' && sync", self.source)
        self.assertIn("Dadurch wird kein Mainboard-Update gestartet", self.source)

    def test_update_status_font_is_one_step_larger(self):
        self.assertIn("flow_font.setPointSize(flow_font.pointSize() + 1)", self.source)
        self.assertIn("flow_font.setPixelSize(flow_font.pixelSize() + 1)", self.source)


if __name__ == "__main__":
    unittest.main()
