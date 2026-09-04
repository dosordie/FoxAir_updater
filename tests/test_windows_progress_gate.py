from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WindowsProgressGateTests(unittest.TestCase):
    def test_release_progress_waits_for_transfer_started(self):
        source = (ROOT / "updater/windows/foxair_updater_release_progress_product.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('status.get("transfer_started") is True', source)
        self.assertIn("self.progress.setValue(0)", source)
        self.assertIn('self.progress.setFormat("0 % – LTE-Modem")', source)

    def test_windows_build_uses_progress_gated_release_entrypoint(self):
        build = (ROOT / "updater/windows/build_windows_portable.bat").read_text(
            encoding="utf-8"
        )
        self.assertIn("foxair_updater_release_progress_product.py", build)


if __name__ == "__main__":
    unittest.main()
