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

    def test_only_traffic_diagnostics_are_persistently_toggleable(self):
        self.assertIn('value("show_modem_diagnostics", "false")', self.desktop)
        self.assertIn('setValue("show_modem_diagnostics", visible)', self.desktop)
        self.assertIn("setTabVisible(self.modem_tab_index, True)", self.desktop)
        toggle = self.desktop.split("def _toggle_modem_diagnostics", 1)[1].split("def ", 1)[0]
        self.assertNotIn("modem_tab_index", toggle)
        self.assertIn("traffic_tab_index", toggle)
        self.assertIn("setTabVisible(self.traffic_tab_index", self.traffic)

    def test_reattach_is_read_only_and_does_not_start_an_ota(self):
        reattach = self.base.split("def _reattach_ota", 1)[1].split("def ", 1)[0]
        self.assertIn('"status"', reattach)
        for forbidden in ("--execute", "PHNIX-FULL-UPDATE", "--manifest", "restore"):
            self.assertNotIn(forbidden, reattach)
        self.assertIn("Keine automatische Aktion ausgeführt", self.base)

    def test_requested_help_and_visual_separation_are_present(self):
        self.assertIn("Was ist das Manifest?", self.base)
        self.assertIn("Das Manifest verändert die Firmwaredatei NICHT", self.base)
        self.assertIn('setObjectName("remoteAdbHelp")', self.base)
        self.assertIn("border:1px solid #d0d5dd", self.base)

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
