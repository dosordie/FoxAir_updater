import unittest
from pathlib import Path


class Issue9ModemMetadataUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path(
            "updater/windows/foxair_updater_operator_display.py"
        ).read_text(encoding="utf-8")
        cls.hook = Path("updater/dtu_ota/payload/phnix_ota_runtime_hook").read_text(
            encoding="utf-8"
        )

    def test_signal_is_labeled_as_csq_with_rssi_estimate(self):
        self.assertIn("-113 + 2 * numeric", self.ui)

    def test_rs485_runtime_diagnostics_are_read_only(self):
        self.assertIn("RS485_RUNTIME_ADDRESS = 0x98914", self.ui)
        self.assertIn("RS485_RUNTIME_SIZE = 24", self.ui)
        self.assertIn("read_process_memory", self.ui)
        self.assertNotIn("uart485_send_data_to_board", self.ui)

    def test_ota_count_up_is_display_only_and_starts_after_cloud_guard(self):
        self.assertIn("minutes, seconds = divmod(elapsed, 60)", self.ui)
        self.assertIn('"c350-probe-attaching"', self.ui)
        self.assertIn("iptables -I OUTPUT -o rmnet_data0 -p tcp --dport 1883 -j DROP", self.hook)


if __name__ == "__main__":
    unittest.main()
