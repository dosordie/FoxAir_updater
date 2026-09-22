import unittest
from pathlib import Path


class WindowsTrafficUiSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("updater/windows/foxair_updater_traffic.py").read_text(encoding="utf-8")

    def test_full_payload_and_direct_table_content(self):
        self.assertIn('tracer.enable(hooks, mode="full")', self.source)
        self.assertNotIn('_traffic_details', self.source)
        self.assertNotIn('QDialog', self.source)
        self.assertNotIn('QTextEdit', self.source)

    def test_ring_is_only_cleared_for_manual_disable_with_delete(self):
        self.assertNotIn("if checked:\n            self._traffic_ring.clear()", self.source)
        self.assertIn('delete_data = action == "disable" and self.traffic_delete.isChecked()', self.source)
        clear_position = self.source.index("self._traffic_ring.clear()")
        guard_position = self.source.rfind("if delete_data:", 0, clear_position)
        self.assertGreater(guard_position, 0)



if __name__ == "__main__":
    unittest.main()
