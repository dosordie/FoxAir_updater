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
        cls.product_ui = Path(
            "updater/windows/foxair_updater_runner_product.py"
        ).read_text(encoding="utf-8")
        cls.release_ui = Path(
            "updater/windows/foxair_updater_release_product.py"
        ).read_text(encoding="utf-8")
        cls.backend_prep = Path(
            "updater/windows/prepare_windows_backend.py"
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

    def test_windows_build_uses_product_entrypoint_and_maintenance_backend(self):
        self.assertIn(
            "updater\\windows\\foxair_updater_release_product.py", self.build
        )
        self.assertIn("import foxair_updater_runner_product as product", self.release_ui)
        self.assertIn('root / "updater/common"', self.backend_prep)
        self.assertIn('backend / "updater/common" / source.name', self.backend_prep)
        self.assertIn("phnix_statistics_counters.py", self.product_ui)

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
            "BOARD_SOFTWARE_VERSION_ADDRESS = 0x935EA",
            "BOARD_HARDWARE_CODE_ADDRESS = 0x935EF",
            "BOARD_HARDWARE_VERSION_ADDRESS = 0x935F8",
            "ICCID_ADDRESS = 0x9365C",
            "IMSI_ADDRESS = 0x93674",
            "IMEI_ADDRESS = 0x93688",
            "MCC_ADDRESS = 0x98022",
            "MNC_ADDRESS = 0x98024",
            "LAC_ADDRESS = 0x98168",
            "CELL_ID_ADDRESS = 0x9816C",
            "SERVING_SYSTEM_ADDRESS = 0x981B4",
        ]
        for marker in expected:
            self.assertIn(marker, self.modem)

    def test_modem_identity_fields_have_explicit_fixed_sizes(self):
        self.assertIn("ICCID_SIZE = 22", self.modem)
        self.assertIn("IMSI_SIZE = 17", self.modem)
        self.assertIn("IMEI_SIZE = 32", self.modem)
        self.assertIn("BOARD_INFO_SIZE = 28", self.modem)

    def test_lte_diagnostics_formats_current_modem_info(self):
        for marker in (
            "<h3>Mainboard</h3>",
            "Firmware:",
            "<h3>Modem</h3>",
            "IMEI:",
            "<h3>SIM</h3>",
            "ICCID:",
            "Netzkennung MCC / MNC:",
            "MQTT / Cloud:",
            "ErrorStatue Bitmap:",
        ):
            self.assertIn(marker, self.lte_ui)

    def test_operator_decoder_stays_read_only(self):
        self.assertIn("OPERATORS", self.operators)
        self.assertIn("lookup_operator", self.operators)
        self.assertNotIn("adb", self.operators.lower())
        self.assertNotIn("shell", self.operators.lower())

    def test_statistics_maintenance_has_explicit_write_confirmation(self):
        self.assertIn("PHNIX-STATISTICS-WRITE", self.maintenance)
        self.assertIn("--confirm", self.maintenance)
        self.assertIn("--execute", self.maintenance)
        self.assertIn("confirm", self.maintenance_ui)

    def test_base_ui_does_not_write_modem_info(self):
        self.assertNotIn("/proc/", self.base_ui)
        self.assertNotIn("dd if=/proc", self.app_ui)


if __name__ == "__main__":
    unittest.main()
