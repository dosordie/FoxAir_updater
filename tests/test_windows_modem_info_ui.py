import unittest
from pathlib import Path


class WindowsModemInfoUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.desktop = Path("updater/windows/foxair_updater_desktop.py").read_text(encoding="utf-8")
        cls.modem = Path("updater/common/phnix_modem_info.py").read_text(encoding="utf-8")
        cls.build = Path("updater/windows/build_windows_portable.bat").read_text(encoding="utf-8")

    def test_windows_build_uses_extended_desktop_entrypoint(self):
        self.assertIn("updater\\windows\\foxair_updater_desktop.py", self.build)

    def test_modem_info_is_read_only_process_memory_diagnostics(self):
        self.assertIn('"Modem Info / LTE Diagnose"', self.desktop)
        self.assertIn("read_phnix_modem_info", self.desktop)
        self.assertIn("dd if=/proc/{pid}/mem", self.modem)
        self.assertNotIn("/dev/ttyHSL2", self.modem)
        self.assertNotIn("FC03", self.modem)
        self.assertNotIn("of=/proc/", self.modem)

    def test_live_confirmed_addresses_are_encoded(self):
        self.assertIn("ERROR_STATUS_ADDRESS = 0x93124", self.modem)
        self.assertIn("STATISTICS_ADDRESS = 0x91B60", self.modem)
        self.assertIn("BOARD_INFO_ADDRESS = 0x935E1", self.modem)
        self.assertIn("BOARD_INFO_SIZE = 28", self.modem)

    def test_unverified_ascii_candidate_is_not_presented_as_confirmed_id(self):
        self.assertIn("unverified_device_id_candidate", self.modem)
        self.assertIn("stabile Zuordnung im Binary noch offen", self.desktop)
        self.assertIn("wird bewusst nicht als ID ausgegeben", self.desktop)

    def test_advanced_block_reset_only_deletes_local_pending_marker(self):
        self.assertIn('QCheckBox("Blockzustand zurücksetzen erlauben")', self.desktop)
        self.assertIn('"cache.pending"', self.desktop)
        self.assertIn("marker.unlink()", self.desktop)
        self.assertIn("keine ADB- oder Mainboard-Operation", self.desktop)

    def test_completed_flow_phases_are_resolved_to_green(self):
        self.assertIn('self._set_step(key, "ok", text)', self.desktop)
        self.assertIn('self._resolve_flow_step("phase-yield"', self.desktop)
        self.assertIn('self._resolve_flow_step("phase-c350"', self.desktop)
        self.assertIn('self._resolve_flow_step("phase-c5a8"', self.desktop)


if __name__ == "__main__":
    unittest.main()
