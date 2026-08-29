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

    def test_mqtt_stays_connected_by_default_and_can_be_explicitly_isolated(self):
        update_ui = self.base.split("def _update(self):", 1)[1].split("def _status", 1)[0]
        advanced_ui = self.base.split("def _advanced(self):", 1)[1].split("def _load", 1)[0]
        update_run = self.base.split("def _update_run(self):", 1)[1].split("def _restore", 1)[0]

        self.assertNotIn("self.isolate_mqtt", update_ui)
        self.assertIn('QCheckBox("MQTT bei Update aus")', advanced_ui)
        self.assertIn('value("isolate_mqtt", "false")', advanced_ui)
        self.assertIn('setValue("isolate_mqtt", checked)', advanced_ui)
        self.assertIn("etwa 30 Minuten", advanced_ui)
        self.assertEqual(update_run.count('update_args.append("--isolate-mqtt")'), 1)
        self.assertIn("if self.isolate_mqtt.isChecked():", update_run)
        default_args = update_run.split("if self.isolate_mqtt.isChecked():", 1)[0]
        self.assertNotIn('"--isolate-mqtt"', default_args)

    def test_firmware_update_is_not_presented_as_experimental(self):
        visible_sources = self.base + self.app + self.desktop + self.traffic + self.maintenance
        for obsolete in (
            "EXPERIMENTELL",
            "Experimentell",
            "experimentelles Firmwareupdate",
            "Echter Versionswechsel noch nicht live validiert",
            "Experimentelles Update",
        ):
            self.assertNotIn(obsolete, visible_sources)
        self.assertIn('setWindowTitle(f"FoxAir Updater {APP_VERSION}")', self.base)
        self.assertIn("Firmwareupdate – Nutzung auf eigenes Risiko", self.base)
        self.assertIn("Risiko des Firmwareupdates verstanden.", self.base)
        self.assertIn('"Firmwareupdate starten"', self.base)

    def test_runtime_restore_wait_has_neutral_cloud_status(self):
        self.assertIn('"runtime-restore-wait"', self.app + self.maintenance)
        self.assertIn("normaler LTE-/Cloudzustand wird geprüft", self.app + self.maintenance)
        self.assertNotIn("warte auf Wiederverbindung von MQTT", self.app + self.maintenance)
        self.assertNotIn("Cloud wird wieder verbunden", self.app + self.maintenance)

    def test_maintenance_is_neutrally_named(self):
        self.assertIn("Wartung – Mainboard OTA-Vorgänge", self.maintenance)
        self.assertNotIn("Experimentelle Wartung – Mainboard OTA-Vorgänge", self.maintenance)


if __name__ == "__main__":
    unittest.main()
