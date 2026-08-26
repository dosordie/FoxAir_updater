import unittest
from pathlib import Path


class Issue9ModemMetadataUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path(
            "updater/windows/foxair_updater_operator_display.py"
        ).read_text(encoding="utf-8")
        cls.hook = Path("tools/phnix_ota/phnix_ota_runtime_hook").read_text(
            encoding="utf-8"
        )

    def test_signal_is_labeled_as_csq_with_rssi_estimate(self):
        self.assertIn("CSQ {text} / 31 (~ {rssi} dBm)", self.ui)
        self.assertIn("-113 + 2 * numeric", self.ui)
        self.assertIn("≥ -51 dBm", self.ui)
        self.assertIn("CSQ 0 = ungültiger/Initialwert", self.ui)

    def test_statistics_use_verified_meanings(self):
        self.assertIn("Uplink-Telegramme", self.ui)
        self.assertIn("Downlink-Telegramme", self.ui)
        self.assertIn("DTU-OTA-Vorgänge", self.ui)
        self.assertIn("Mainboard OTA-Vorgänge", self.ui)
        self.assertIn("phnixIot4G-Starts (Power-Reset-t)", self.ui)
        self.assertIn("Vom LTE-Dienst ausgelöste Reboots", self.ui)
        self.assertIn("mehr als 30 Minuten", self.ui)
        self.assertIn("Remote-RESET-Befehl", self.ui)

    def test_rs485_runtime_diagnostics_are_read_only(self):
        self.assertIn("RS485_RUNTIME_ADDRESS = 0x98914", self.ui)
        self.assertIn("RS485_RUNTIME_SIZE = 24", self.ui)
        self.assertIn("read_process_memory", self.ui)
        self.assertIn("Board-Service-Health", self.ui)
        self.assertIn("Letzter 0x63-Traffic", self.ui)
        self.assertIn("Letztes gültiges 0x63-Frame", self.ui)
        self.assertIn("RS485-Fehlerstatus", self.ui)
        self.assertIn("Board-Service-/Health-Timeout", self.ui)
        self.assertIn("kein CRC-gültiges 0x63-Frame seit ~420 s", self.ui)
        self.assertNotIn("uart485_send_data_to_board", self.ui)

    def test_cloud_status_uses_verified_bit_10_meaning(self):
        self.assertIn("Aliyun/MQTT aktuell nicht verbunden", self.ui)
        self.assertIn("Cloud-/MQTT-Fehlerstatus", self.ui)

    def test_ota_count_up_is_display_only_and_starts_after_cloud_guard(self):
        self.assertIn("Verstrichen: --:--", self.ui)
        self.assertIn("minutes, seconds = divmod(elapsed, 60)", self.ui)
        self.assertIn('"c350-probe-attaching"', self.ui)
        self.assertIn("Keine automatische Bewertung oder Abbruchlogik", self.ui)
        self.assertIn("iptables -I OUTPUT -o rmnet_data0 -p tcp --dport 1883 -j DROP", self.hook)


if __name__ == "__main__":
    unittest.main()
