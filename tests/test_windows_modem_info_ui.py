import unittest
from pathlib import Path


class WindowsModemInfoUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.desktop = Path("updater/windows/foxair_updater_desktop.py").read_text(
            encoding="utf-8"
        )
        cls.lte_ui = Path("updater/windows/foxair_updater_lte_diagnostics.py").read_text(
            encoding="utf-8"
        )
        cls.operator_ui = Path(
            "updater/windows/foxair_updater_operator_display.py"
        ).read_text(encoding="utf-8")
        cls.maintenance_ui = Path(
            "updater/windows/foxair_updater_maintenance.py"
        ).read_text(encoding="utf-8")
        cls.operators = Path("updater/common/network_operators.py").read_text(
            encoding="utf-8"
        )
        cls.modem = Path("updater/common/phnix_modem_info.py").read_text(
            encoding="utf-8"
        )
        cls.maintenance = Path(
            "updater/common/phnix_statistics_maintenance.py"
        ).read_text(encoding="utf-8")
        cls.transport = Path("updater/common/adb_transport.py").read_text(
            encoding="utf-8"
        )
        cls.base_ui = Path("updater/windows/foxair_updater_gui.py").read_text(
            encoding="utf-8"
        )
        cls.app_ui = Path("updater/windows/foxair_updater_app.py").read_text(encoding="utf-8")
        cls.traffic_ui = Path(
            "updater/windows/foxair_updater_traffic.py"
        ).read_text(encoding="utf-8")
        cls.build = Path("updater/windows/build_windows_portable.bat").read_text(
            encoding="utf-8"
        )

    def test_windows_build_uses_maintenance_entrypoint(self):
        self.assertIn(
            "updater\\windows\\foxair_updater_maintenance.py", self.build
        )
        self.assertIn(
            "backend\\updater\\common\\phnix_statistics_maintenance.py",
            self.build,
        )

    def test_modem_info_is_read_only_process_memory_diagnostics(self):
        self.assertIn('"Modem Info / LTE Diagnose"', self.desktop)
        self.assertIn("read_phnix_modem_info", self.lte_ui)
        self.assertIn("dd if=/proc/{pid}/mem", self.modem)
        self.assertIn("| od -An -v -tx1", self.modem)
        self.assertNotIn("/dev/ttyHSL2", self.modem)
        self.assertNotIn("FC03", self.modem)
        self.assertNotIn("of=/proc/", self.modem)

    def test_windows_adb_processes_do_not_flash_console_windows(self):
        self.assertIn("CREATE_NO_WINDOW", self.transport)
        self.assertIn("creationflags=self._creationflags()", self.transport)

    def test_main_window_is_wider_and_traffic_actions_reach_program_log(self):
        self.assertIn("self.resize(1100, 780)", self.base_ui)
        self.assertIn('self._log("[Modem Diagnose / Traffic] "', self.traffic_ui)
        self.assertIn("Diagnose ist aktiv und passiv angehängt", self.traffic_ui)
        self.assertIn("Aktualisierung abgeschlossen", self.traffic_ui)
        self.assertIn('self._log("[Modem Diagnose / Traffic] Fehler: "', self.traffic_ui)

    def test_live_confirmed_lte_addresses_are_encoded(self):
        expected = [
            "ERROR_STATUS_ADDRESS = 0x93124",
            "STATISTICS_ADDRESS = 0x91B60",
            "BOARD_SOFTWARE_CODE_ADDRESS = 0x935E1",
            "ICCID_ADDRESS = 0x9365C",
            "IMSI_ADDRESS = 0x93674",
            "IMEI_ADDRESS = 0x93688",
            "PCLIENT_POINTER_ADDRESS = 0x94EB4",
            "ROAMING_VALID_ADDRESS = 0x97FE8",
            "CURRENT_PLMN_VALID_ADDRESS = 0x98020",
            "LAC_ADDRESS = 0x98168",
            "CELL_ID_ADDRESS = 0x9816C",
            "SERVING_SYSTEM_ADDRESS = 0x981B4",
            "MODE_TYPE_ADDRESS = 0x98912",
            "DEVICE_SECRET_ADDRESS = 0x9896C",
            "PRODUCT_SECRET_ADDRESS = 0x989B0",
            "DEVICE_NAME_ADDRESS = 0x98A58",
            "PRODUCT_KEY_ADDRESS = 0x98A98",
            "SIM_STATUS_ADDRESS = 0x98AB0",
        ]
        for text in expected:
            self.assertIn(text, self.modem)

    def test_ui_has_requested_sections_and_secret_masking(self):
        for heading in (
            "<h3>Mainboard</h3>",
            "<h3>Modem</h3>",
            "<h3>SIM</h3>",
            "<h3>Mobilfunk</h3>",
            "<h3>Netzwerk</h3>",
            "<h3>Cloud</h3>",
            "<h3>Statistik / Fehler</h3>",
        ):
            self.assertIn(heading, self.lte_ui)
        self.assertIn('QCheckBox("Cloud-Secrets anzeigen")', self.lte_ui)
        self.assertIn("••••••••••••••••", self.lte_ui)
        self.assertIn("Mobilfunk-IP / PDP-IP", self.lte_ui)
        self.assertIn("MQTT / Cloud", self.lte_ui)

    def test_operator_ui_shows_current_and_home_network(self):
        self.assertIn("Aktueller Netzbetreiber", self.operator_ui)
        self.assertIn("Heimatnetz (aus IMSI)", self.operator_ui)
        self.assertIn("Netzbeschreibung (Modem)", self.operator_ui)
        self.assertIn('(262, 1): "Telekom Deutschland GmbH"', self.operators)
        self.assertIn('(208, 1): "Orange France"', self.operators)

    def test_mainboard_ota_counter_is_presented_as_operations_with_tooltip(self):
        self.assertIn("Mainboard OTA-Vorgänge", self.operator_ui)
        self.assertIn("Vom LTE-Modul gezählte OTA-Aufträge", self.operator_ui)
        self.assertIn('href="ota-counter"', self.operator_ui)
        self.assertIn("linkHovered", self.operator_ui)

    def test_statistics_write_ui_is_only_a_frontend_for_shared_core(self):
        self.assertIn(
            "import foxair_updater_operator_display as operator", self.maintenance_ui
        )
        self.assertIn(
            '"phnix_statistics_maintenance.py"', self.maintenance_ui
        )
        self.assertIn(
            '"set-mainboard-ota-count"', self.maintenance_ui
        )
        self.assertIn(
            '"PHNIX-STATISTICS-WRITE"', self.maintenance_ui
        )
        self.assertIn(
            "Ändern des persistenten Statistikzustands erlauben",
            self.maintenance_ui,
        )
        self.assertNotIn("kill -TERM", self.maintenance_ui)
        self.assertNotIn("kill -STOP", self.maintenance_ui)
        self.assertNotIn("REMOTE_STATISTICS", self.maintenance_ui)
        self.assertIn("kill -TERM", self.maintenance)
        self.assertIn("kill -STOP", self.maintenance)

    def test_unverified_ascii_candidate_is_not_presented_as_confirmed_id(self):
        self.assertIn("unverified_device_id_candidate", self.modem)
        self.assertNotIn("Device-/DTU-ID:", self.lte_ui)

    def test_advanced_block_reset_uses_safe_controller_restore(self):
        self.assertIn(
            'QCheckBox("Blockzustand zurücksetzen erlauben")', self.desktop
        )
        self.assertIn('"cache.pending"', self.desktop)
        self.assertNotIn("marker.unlink()", self.desktop)
        self.assertIn("dirty_state_reset_is_safe", self.desktop)
        self.assertIn('self._backend("restore"', self.desktop)

    def test_dry_run_dirty_state_bypasses_advanced_opt_in_only_for_popup(self):
        self.assertIn("def _reset_block_pending(self, checked: bool = False, *, from_dry_run: bool = False)", self.desktop)
        self.assertIn("self._reset_block_pending(from_dry_run=True)", self.desktop)
        self.assertIn("not from_dry_run and not self.allow_block_reset.isChecked()", self.desktop)

    def test_lte_log_contains_translations_and_events_only_refine_existing_steps(self):
        self.assertIn('explained = explain_debug_line(line).splitlines()', self.lte_ui)
        self.assertIn('strftime("%H:%M:%S.%f")[:-3]', self.lte_ui)
        self.assertIn("if key in self._flow_steps:", self.lte_ui)
        for kind in ("transfer-complete", "manufacturer-success", "mqtt-normal"):
            self.assertIn(f'kind == "{kind}"', self.lte_ui)
        self.assertNotIn('kind == "cloud-progress"', self.lte_ui)

    def test_debug_monitor_controls_status_and_update_page_entry(self):
        self.assertIn('self.mode.setCurrentIndex(1)', self.lte_ui)
        self.assertIn('QPushButton("Verbinden")', self.lte_ui)
        self.assertIn('QPushButton("Trennen")', self.lte_ui)
        for status in ("Verbinde …", "Verbunden", "Getrennt", "Verbindung fehlgeschlagen"):
            self.assertIn(status, self.lte_ui + Path("updater/common/phnix_debug.py").read_text(encoding="utf-8"))
        self.assertIn('QPushButton("LTE-Modem-Log öffnen")', self.app_ui)
        self.assertIn('setMinimumHeight(26)', self.base_ui + self.app_ui)
        update_page = self.base_ui.split("def _update(self):", 1)[1].split("def _status", 1)[0]
        self.assertNotIn("Manifest", update_page)
        self.assertIn("Update-Datei", update_page)

    def test_completed_flow_phases_are_resolved_to_green(self):
        self.assertIn('self._set_step(key, "ok", text)', self.desktop)
        self.assertIn('self._resolve_flow_step("phase-yield"', self.desktop)
        self.assertIn('self._resolve_flow_step("phase-c350"', self.desktop)
        self.assertIn('self._resolve_flow_step("phase-c5a8"', self.desktop)


if __name__ == "__main__":
    unittest.main()
