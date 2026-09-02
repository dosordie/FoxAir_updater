import unittest
from pathlib import Path


class WindowsRunnerProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.product = Path("updater/windows/foxair_updater_runner_product.py").read_text(encoding="utf-8")
        cls.build = Path("updater/windows/build_windows_portable.bat").read_text(encoding="utf-8")
        cls.cli = Path("updater/dtu_ota/cli.py").read_text(encoding="utf-8")
        cls.client = Path("updater/dtu_ota/client.py").read_text(encoding="utf-8")

    def test_windows_uses_production_runner_path(self):
        self.assertIn('base.backend_dir() / "updater/dtu_ota/cli.py"', self.product)
        self.assertIn("updater\\windows\\foxair_updater_runner_product.py", self.build)
        self.assertIn("backend\\updater\\dtu_ota\\cli.py", self.build)
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


if __name__ == "__main__":
    unittest.main()
