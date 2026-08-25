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
        self.assertEqual(release_check.parse_version_tuple("windows-v0.1.8"), (0, 1, 8))

    def test_newer_release_comparison(self):
        self.assertTrue(release_check.is_newer_release("0.1.7", "windows-v0.1.8"))
        self.assertFalse(release_check.is_newer_release("0.1.8", "windows-v0.1.8"))
        self.assertFalse(release_check.is_newer_release("0.1.9", "windows-v0.1.8"))

    def test_fetch_latest_release_is_read_only_metadata(self):
        seen = {}

        def fake_urlopen(request, timeout):
            seen["url"] = request.full_url
            seen["timeout"] = timeout
            return FakeResponse(
                {
                    "tag_name": "windows-v0.1.8",
                    "name": "FoxAir Updater Windows v0.1.8",
                    "html_url": "https://github.com/dosordie/FoxAir_updater/releases/tag/windows-v0.1.8",
                }
            )

        value = release_check.fetch_latest_release("0.1.7", urlopen=fake_urlopen)
        self.assertTrue(value["newer"])
        self.assertEqual(value["tag"], "windows-v0.1.8")
        self.assertEqual(seen["url"], release_check.UPDATE_API_URL)
        self.assertEqual(seen["timeout"], 12)

    def test_windows_app_keeps_driver_before_platform_tools_and_persists_requested_values(self):
        source = Path("updater/windows/foxair_updater_app.py").read_text(encoding="utf-8")
        base = Path("updater/windows/foxair_updater_gui.py").read_text(encoding="utf-8")
        self.assertIn('APP_VERSION = "0.2.3"', source)
        self.assertIn("SIMCOM_Windows_USB_Drivers_V1.0.2.zip", source)
        self.assertIn('layout.insertLayout(1, driver_row)', source)
        self.assertIn('self.settings.setValue("adb"', source)
        self.assertIn('self.settings.setValue("backup"', source)
        self.assertIn('self.settings.setValue("remote_host"', source)
        self.assertIn('self.settings.setValue("remote_port"', source)
        self.assertIn('self._remember_parent("manifest_dir"', source)
        self.assertIn('self._remember_parent("firmware_dir"', source)
        self.assertIn('QSettings("FoxAir", "FoxAir Updater")', base)

    def test_remote_settings_are_loaded_before_writeback_signals_are_reenabled(self):
        source = Path("updater/windows/foxair_updater_app.py").read_text(encoding="utf-8")
        load_start = source.index("    def _load(self):")
        connection_start = source.index("    def _connection(self):", load_start)
        load_source = source[load_start:connection_start]

        self.assertIn('remote_host_value = str(self.settings.value("remote_host"', load_source)
        self.assertIn('remote_port_value = int(self.settings.value("remote_port", 5038))', load_source)
        self.assertIn("widget.blockSignals(True)", load_source)
        self.assertIn("self.remote_host.setText(remote_host_value)", load_source)
        self.assertIn("self.remote_port.setValue(remote_port_value)", load_source)
        self.assertIn("widget.blockSignals(False)", load_source)
        self.assertLess(
            load_source.index('remote_host_value = str(self.settings.value("remote_host"'),
            load_source.index("self.adb_remote.setChecked(remote)"),
        )
        self.assertLess(
            load_source.index('remote_port_value = int(self.settings.value("remote_port", 5038))'),
            load_source.index("self.adb_remote.setChecked(remote)"),
        )


if __name__ == "__main__":
    unittest.main()
