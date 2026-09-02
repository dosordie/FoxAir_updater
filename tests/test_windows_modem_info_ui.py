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
            "BOARD_SOFTWARE_CODE_CLOUD_ADDRESS = 0x93615",
            "BOARD_SOFTWARE_VERSION_CLOUD_ADDRESS = 0x9361E",
            "DEVICE_SOFTWARE_CODE_ADDRESS = 0x93764",
            "DEVICE_SOFTWARE_VERSION_ADDRESS = 0x93770",
            "DEVICE_CODE_ADDRESS = 0x9347C",
            "DTU_SOFTWARE_CODE_ADDRESS = 0x9348C",
            "DTU_SOFTWARE_VERSION_ADDRESS = 0x93498",
            "DTU_HARDWARE_CODE_ADDRESS = 0x934A4",
            "SOCKET_STATUS_ADDRESS = 0x93038",
            "GSM_STATUS_ADDRESS = 0x93040",
        ]
        for marker in expected:
            self.assertIn(marker, self.modem)

    def test_modem_info_uses_fixed_width_device_code(self):
        self.assertIn("DEVICE_CODE_SIZE = 15", self.modem)
        self.assertIn("read_c_string(data, offset, size)", self.modem)
        self.assertNotIn("DEVICE_CODE_SIZE = 16", self.modem)

    def test_lte_diagnostics_formats_modem_info(self):
        self.assertIn('"Gerätecode"', self.lte_ui)
        self.assertIn('"DTU Software"', self.lte_ui)
        self.assertIn('"DTU Hardware"', self.lte_ui)
        self.assertIn('"Mainboard aktuell"', self.lte_ui)
        self.assertIn('"Mainboard Cloud"', self.lte_ui)
        self.assertIn('"Fehlerstatus"', self.lte_ui)
        self.assertIn('"Socket Status"', self.lte_ui)
        self.assertIn('"GSM Status"', self.lte_ui)

    def test_operator_decoder_stays_read_only(self):
        self.assertIn("MCC_MNC_TO_OPERATOR", self.operators)
        self.assertIn("operator_name", self.operators)
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
