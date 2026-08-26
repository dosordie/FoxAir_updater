import unittest
from pathlib import Path


class V030GuiRequirementsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Path("updater/windows/foxair_updater_gui.py").read_text(encoding="utf-8")
        cls.app = Path("updater/windows/foxair_updater_app.py").read_text(encoding="utf-8")
        cls.desktop = Path("updater/windows/foxair_updater_desktop.py").read_text(encoding="utf-8")
        cls.traffic = Path("updater/windows/foxair_updater_traffic.py").read_text(encoding="utf-8")
        cls.maintenance = Path("updater/windows/foxair_updater_maintenance.py").read_text(encoding="utf-8")

    def test_base_tab_order(self):
        labels = ["Verbindung", "Backup", "Firmware Update", "Manifest", "Status / Recovery", "Erweitert"]
        positions = [self.base.index(f'"{label}"') for label in labels]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('insertTab(\n            5, self._modem_info_page()', self.desktop)

    def test_diagnostics_are_hidden_and_persistently_toggleable(self):
        self.assertIn('value("show_modem_diagnostics", "false")', self.desktop)
        self.assertIn('setValue("show_modem_diagnostics", visible)', self.desktop)
        self.assertIn("setTabVisible(self.modem_tab_index", self.desktop)
        self.assertIn("setTabVisible(self.traffic_tab_index", self.traffic)

    def test_modem_and_maintenance_actions_follow_busy_state(self):
        combined = self.desktop + self.app + self.maintenance + self.traffic
        for text in (
            "not self.busy and not self._modem_info_running",
            "self.allow_block_reset.setEnabled(not self.busy)",
            "self.cache_copy_btn.setEnabled(not self.busy",
            "self.allow_statistics_write.setEnabled(not self.busy)",
            "enabled = not self.busy and not self._traffic_running",
        ):
            self.assertIn(text, combined)

    def test_enduser_same_version_controls_are_removed(self):
        self.assertNotIn('QPushButton("Gleichversionstest starten")', self.base)
        self.assertNotIn('QCheckBox("Passiver RS485-Logger läuft tatsächlich")', self.base)

    def test_maintenance_is_neutrally_named(self):
        self.assertIn("Wartung – Mainboard OTA-Vorgänge", self.maintenance)
        self.assertNotIn("Experimentelle Wartung – Mainboard OTA-Vorgänge", self.maintenance)


if __name__ == "__main__":
    unittest.main()
