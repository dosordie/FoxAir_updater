import json
import unittest
from pathlib import Path

from updater.windows import release_check


class FakeResponse:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._raw


class WindowsReleaseCheckTests(unittest.TestCase):
    def test_windows_release_tag_parses(self):
        self.assertEqual(release_check.parse_version_tuple("windows-v0.1.6"), (0, 1, 6))

    def test_newer_release_comparison(self):
        self.assertTrue(release_check.is_newer_release("0.1.5", "windows-v0.1.6"))
        self.assertFalse(release_check.is_newer_release("0.1.6", "windows-v0.1.6"))
        self.assertFalse(release_check.is_newer_release("0.1.7", "windows-v0.1.6"))

    def test_fetch_latest_release_is_read_only_metadata(self):
        seen = {}

        def fake_urlopen(request, timeout):
            seen["url"] = request.full_url
            seen["timeout"] = timeout
            return FakeResponse(
                {
                    "tag_name": "windows-v0.1.6",
                    "name": "FoxAir Updater Windows v0.1.6",
                    "html_url": "https://github.com/dosordie/FoxAir_updater/releases/tag/windows-v0.1.6",
                }
            )

        value = release_check.fetch_latest_release("0.1.5", urlopen=fake_urlopen)
        self.assertTrue(value["newer"])
        self.assertEqual(value["tag"], "windows-v0.1.6")
        self.assertEqual(seen["url"], release_check.UPDATE_API_URL)
        self.assertEqual(seen["timeout"], 12)

    def test_windows_app_keeps_driver_before_platform_tools_and_persists_requested_values(self):
        source = Path("updater/windows/foxair_updater_app.py").read_text(encoding="utf-8")
        base = Path("updater/windows/foxair_updater_gui.py").read_text(encoding="utf-8")
        self.assertIn("SIMCOM_Windows_USB_Drivers_V1.0.2.zip", source)
        self.assertIn('layout.insertLayout(1, driver_row)', source)
        self.assertIn('self.settings.setValue("adb"', source)
        self.assertIn('self.settings.setValue("backup"', source)
        self.assertIn('self.settings.setValue("remote_host"', source)
        self.assertIn('self.settings.setValue("remote_port"', source)
        self.assertIn('self._remember_parent("manifest_dir"', source)
        self.assertIn('self._remember_parent("firmware_dir"', source)
        self.assertIn('QSettings("FoxAir", "FoxAir Updater")', base)


if __name__ == "__main__":
    unittest.main()
