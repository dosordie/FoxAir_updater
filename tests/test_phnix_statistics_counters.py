import unittest
from pathlib import Path

from updater.common.phnix_statistics_counters import (
    COUNTERS,
    CounterMaintenanceError,
    counter_value,
    counter_values,
    prepare_patch,
)


class StatisticsCounterMaintenanceTests(unittest.TestCase):
    @staticmethod
    def fixture(**values: int) -> bytes:
        raw = bytearray(128)
        defaults = {
            "dtu_ota": 3,
            "mainboard_ota": 7,
            "power_reset": 11,
            "active_reset": 2,
        }
        defaults.update(values)
        for key, value in defaults.items():
            offset = COUNTERS[key][0]
            raw[offset : offset + 4] = value.to_bytes(4, "little")
        return bytes(raw)

    def test_known_counter_offsets_are_contiguous_uint32_fields(self):
        self.assertEqual(COUNTERS["dtu_ota"][0], 0x20)
        self.assertEqual(COUNTERS["mainboard_ota"][0], 0x24)
        self.assertEqual(COUNTERS["power_reset"][0], 0x28)
        self.assertEqual(COUNTERS["active_reset"][0], 0x2C)

    def test_power_reset_is_preserved_when_another_counter_changes(self):
        raw = self.fixture(power_reset=11, mainboard_ota=7)
        patched, desired = prepare_patch(raw, {"mainboard_ota": 9})
        self.assertEqual(desired["mainboard_ota"], 9)
        self.assertEqual(desired["power_reset"], 11)
        self.assertEqual(counter_value(patched, "mainboard_ota"), 9)
        # phnixIot4G increments this once on the mandatory restart.
        self.assertEqual(counter_value(patched, "power_reset"), 10)
        self.assertEqual(counter_value(patched, "dtu_ota"), 3)
        self.assertEqual(counter_value(patched, "active_reset"), 2)

    def test_requested_power_reset_is_predecremented_for_final_value(self):
        raw = self.fixture(power_reset=20)
        patched, desired = prepare_patch(raw, {"power_reset": 5, "active_reset": 1})
        self.assertEqual(desired["power_reset"], 5)
        self.assertEqual(counter_value(patched, "power_reset"), 4)
        self.assertEqual(desired["active_reset"], 1)
        self.assertEqual(counter_value(patched, "active_reset"), 1)

    def test_power_reset_zero_is_rejected(self):
        with self.assertRaises(CounterMaintenanceError):
            prepare_patch(self.fixture(), {"power_reset": 0})

    def test_patch_does_not_touch_unknown_statistics_bytes(self):
        raw = bytearray(range(128))
        for key, value in {
            "dtu_ota": 3,
            "mainboard_ota": 7,
            "power_reset": 11,
            "active_reset": 2,
        }.items():
            offset = COUNTERS[key][0]
            raw[offset : offset + 4] = value.to_bytes(4, "little")
        original = bytes(raw)
        patched, _desired = prepare_patch(original, {"dtu_ota": 4})
        allowed = set(range(0x20, 0x24)) | set(range(0x28, 0x2C))
        for index, (before, after) in enumerate(zip(original, patched)):
            if index not in allowed:
                self.assertEqual(before, after, f"unexpected change at 0x{index:02X}")

    def test_final_product_exposes_only_known_event_counters(self):
        product = Path("updater/windows/foxair_updater_runner_product.py").read_text(
            encoding="utf-8"
        )
        for text in (
            "DTU-OTA-Vorgänge",
            "Mainboard OTA-Vorgänge",
            "Dienststarts (Power-Reset-t)",
            "Aktive Modem-Neustarts (Active-Reset-t)",
            "phnix_statistics_counters.py",
            "leer = unverändert",
        ):
            self.assertIn(text, product)
        self.assertIn("power_reset_compensated", Path(
            "updater/common/phnix_statistics_counters.py"
        ).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
