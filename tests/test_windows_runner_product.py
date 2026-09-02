import unittest
from pathlib import Path


class WindowsRunnerProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.product = Path("updater/windows/foxair_updater_runner_product.py").read_text(encoding="utf-8")
        cls.release = Path("updater/windows/foxair_updater_release_product.py").read_text(encoding="utf-8")
        cls.prepare = Path("updater/windows/prepare_windows_backend.py").read_text(encoding="utf-8")
        cls.build = Path("updater/windows/build_windows_portable.bat").read_text(encoding="utf-8")
        cls.cli = Path("updater/dtu_ota/cli.py").read_text(encoding="utf-8")
        cls.client = Path("updater/dtu_ota/client.py").read_text(encoding="utf-8")

    def test_windows_uses_production_runner_path(self):
        self.assertIn('base.backend_dir() / "updater/dtu_ota/cli.py"', self.product)
        self.assertIn("updater\\windows\\foxair_updater_release_product.py", self.build)
        self.assertIn("import foxair_updater_runner_product as product", self.release)
        self.assertIn('root / "updater/dtu_ota"', self.prepare)
        self.assertNotIn("backend\\tools\\dtu_ota_runner", self.build)

    def test_relocated_cli_imports_production_package(self):
        self.assertIn("from updater.dtu_ota.client import DtuOtaClient", self.cli)
        self.assertIn("from updater.dtu_ota.package import PackageError", self.cli)
        self.assertNotIn("tools.dtu_ota_runner", self.cli)

    def test_client_uses_relocated_payload(self):
        self.assertIn('self.source_root / "updater/dtu_ota/payload"', self.client)
        self.assertIn('payload / "dtu_ota_supervisor.sh"', self.client)
        self.assertIn('payload / "phnix_ota_runtime_hook"', self.client)
        self.assertNotIn("tools/dtu_ota_runner", self.client)

    def test_serial_progress_is_accepted_for_autonomous_runner(self):
        method = self.product.split("def _update_debug_line", 1)[1].split("def _debug_status", 1)[0]
        self.assertIn('getattr(event, "kind", None) == "transfer-progress"', method)
        self.assertIn("self._phnix_transfer_event = event", method)
        self.assertIn("self._render_transfer_progress()", method)
        self.assertNotIn('"phase-c5a8" in self._flow_steps', method)

    def test_stale_serial_progress_falls_back_to_runner(self):
        self.assertIn("SERIAL_PROGRESS_STALE_SECONDS = 15.0", self.product)
        self.assertIn("def _expire_stale_serial_progress", self.product)
        self.assertIn("self._runner_transfer_visible", self.product)

    def test_product_reuses_runner_flow_rows_instead_of_duplicate_bullets(self):
        self.assertIn('"runner-preflight-user": "runner-preflight"', self.product)
        self.assertIn('"runner-terminal-user": "runner-terminal"', self.product)
        method = self.product.split("def _set_step", 1)[1].split("def _render_runner_status", 1)[0]
        self.assertIn("self.FLOW_KEY_ALIASES.get(key, key)", method)

    def test_manual_preflight_does_not_repeat_phase_below_flow_box(self):
        method = self.product.split("def _render_runner_status", 1)[1].split("def _update_debug_line", 1)[0]
        self.assertIn('phase == "dry-run-complete"', method)
        self.assertIn("not self._runner_autostart_after_prepare", method)
        self.assertIn('self._flow_title = "Vorprüfung erfolgreich"', method)
        self.assertIn("self.progress_text.clear()", method)
        self.assertIn("self.progress_sources.clear()", method)

    def test_verified_service_restart_is_presented_as_completed(self):
        method = self.product.split("def _render_runner_status", 1)[1].split("def _update_debug_line", 1)[0]
        self.assertIn('status.get("service_restart_requested") is True', method)
        self.assertIn('status.get("service_restart_verified") is True', method)
        self.assertIn("LTE-Kommunikationsdienst wurde kontrolliert neu gestartet.", method)

    def test_product_moves_status_button_to_protocol_toolbar(self):
        ui = self.product.split("def _ui(self):", 1)[1].split("# ------------------------------------------------------------------\n    # Final maintenance UI", 1)[0]
        self.assertIn('button.text() == "Protokoll leeren"', ui)
        self.assertIn("source_layout.removeWidget(self.ota_reattach_btn)", ui)
        self.assertIn("log_toolbar.insertWidget", ui)

    def test_product_places_manifest_immediately_before_advanced(self):
        ui = self.product.split("def _ui(self):", 1)[1].split("# ------------------------------------------------------------------\n    # Final maintenance UI", 1)[0]
        self.assertIn('self.tabs.tabText(index) == "Update-Datei / Manifest"', ui)
        self.assertIn('self.tabs.tabText(index) == "Erweitert"', ui)
        self.assertIn("self.tabs.insertTab(advanced_index, manifest_widget, manifest_text)", ui)


if __name__ == "__main__":
    unittest.main()
