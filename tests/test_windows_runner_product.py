import unittest
from pathlib import Path


class WindowsRunnerProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.product = Path("updater/windows/foxair_updater_runner_product.py").read_text(encoding="utf-8")
        cls.enduser = Path("updater/windows/foxair_updater_runner_enduser.py").read_text(encoding="utf-8")
        cls.runner = Path("updater/windows/foxair_updater_runner_gui.py").read_text(encoding="utf-8")
        cls.user_runner = Path("updater/windows/foxair_updater_runner_user_gui.py").read_text(encoding="utf-8")
        cls.base_gui = Path("updater/windows/foxair_updater_gui.py").read_text(encoding="utf-8")
        cls.release = Path("updater/windows/foxair_updater_release_product.py").read_text(encoding="utf-8")
        cls.runtime = Path("updater/windows/foxair_updater_release_runtime.py").read_text(encoding="utf-8")
        cls.windows_readme = Path("updater/windows/README.md").read_text(encoding="utf-8")
        cls.prepare = Path("updater/windows/prepare_windows_backend.py").read_text(encoding="utf-8")
        cls.build = Path("updater/windows/build_windows_portable.bat").read_text(encoding="utf-8")
        cls.cli = Path("updater/dtu_ota/cli.py").read_text(encoding="utf-8")
        cls.client = Path("updater/dtu_ota/client.py").read_text(encoding="utf-8")

    def test_windows_uses_production_runner_path(self):
        self.assertIn('base.backend_dir() / "updater/dtu_ota/cli.py"', self.product)
        self.assertIn("updater\\windows\\foxair_updater_release_runtime.py", self.build)
        self.assertIn("import foxair_updater_release_product as release", self.runtime)
        self.assertIn("import foxair_updater_runner_product as product", self.release)
        self.assertIn('root / "updater/dtu_ota"', self.prepare)
        self.assertNotIn("backend\\tools\\dtu_ota_runner", self.build)

    def test_source_start_uses_same_final_release_entrypoint_as_build(self):
        self.assertIn("updater\\windows\\foxair_updater_release_runtime.py", self.build)
        self.assertIn("import foxair_updater_release_product as release", self.runtime)
        self.assertIn("import foxair_updater_runner_product as product", self.release)

    def test_direct_runner_product_start_delegates_to_final_release_runtime(self):
        self.assertIn(
            "import foxair_updater_release_runtime as release_runtime",
            self.product,
        )
        self.assertIn(
            "raise SystemExit(release_runtime.main())",
            self.product,
        )

    def test_relocated_cli_imports_production_package(self):
        self.assertIn("from updater.dtu_ota.client import DtuOtaClient", self.cli)
        self.assertIn("from updater.dtu_ota.package import PackageError", self.cli)
        self.assertNotIn("tools.dtu_ota_runner", self.cli)

    def test_client_uses_relocated_payload(self):
        self.assertIn('self.source_root / "updater/dtu_ota/payload"', self.client)
        self.assertIn('payload / "dtu_ota_supervisor.sh"', self.client)
        self.assertIn('payload / "phnix_ota_runtime_hook"', self.client)
        self.assertNotIn("tools/dtu_ota_runner", self.client)

    def test_final_layer_owns_transfer_progress_widgets(self):
        self.assertIn("self._owns_transfer_progress = True", self.enduser)
        runner_status = self.runner.split("def _render_runner_status", 1)[1].split(
            "def _show_terminal_result", 1
        )[0]
        self.assertIn('getattr(self, "_owns_transfer_progress", False)', runner_status)
        self.assertIn("and not progress_owned", runner_status)

        user_status = self.user_runner.split("def _render_runner_status", 1)[1].split(
            "def _failed_run_id", 1
        )[0]
        self.assertIn(
            'not getattr(self, "_owns_transfer_progress", False)',
            user_status,
        )

    def test_transfer_progress_is_monotonic_and_ui_throttled(self):
        method = self.enduser.split("def _render_transfer_progress", 1)[1].split(
            "def _show_terminal_result", 1
        )[0]
        self.assertIn("_display_progress_high_watermark = max(", method)
        self.assertIn("PROGRESS_UI_MIN_INTERVAL", method)
        self.assertIn("QTimer.singleShot", method)
        self.assertIn("def _flush_transfer_progress", method)

    def test_runner_machine_output_does_not_stream_pretty_json_to_ui(self):
        runner_call = self.enduser.split("def _run_runner", 1)[1].split(
            "def _log_runner_id_once", 1
        )[0]
        self.assertIn("op in self.QUIET_RUNNER_OPS", runner_call)
        self.assertIn("emit_lines=False", runner_call)
        self.assertIn("self._passive_runner_poll", runner_call)

        done = self.enduser.split("def _done", 1)[1].split("def main", 1)[0]
        self.assertIn("op in self.QUIET_RUNNER_OPS", done)
        self.assertIn("_write_automatic_log_only", done)

        run_method = self.base_gui.split("def _run(self, op, command, cwd=None", 1)[1].split(
            "def _run_sequence", 1
        )[0]
        self.assertIn("if emit_lines:", run_method)
        self.assertIn("if log_command:", run_method)

    def test_runner_progress_waits_for_valid_persisted_length(self):
        method = self.enduser.split("def _render_transfer_progress", 1)[1].split(
            "def _show_terminal_result", 1
        )[0]
        self.assertIn("runner_progress_valid = (", method)
        self.assertIn("runner_length > 0", method)
        self.assertIn("elif self._runner_transfer_visible:", method)

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
        self.assertIn("self.progress_text.clear()", method)
        self.assertIn("self.progress_sources.clear()", method)

    def test_terminal_result_does_not_repeat_below_progress_bar(self):
        status_method = self.enduser.split("def _render_runner_status", 1)[1].split(
            "def _done", 1
        )[0]
        self.assertIn(
            'if terminal and hasattr(self, "progress_sources"):',
            status_method,
        )
        self.assertIn("self.progress_sources.clear()", status_method)

        transfer_method = self.enduser.split(
            "def _render_transfer_progress", 1
        )[1].split("def _show_terminal_result", 1)[0]
        self.assertIn("if self._runner_terminal:", transfer_method)
        self.assertIn("self.progress_sources.clear()", transfer_method)

        user = Path(
            "updater/windows/foxair_updater_runner_user_gui.py"
        ).read_text(encoding="utf-8")
        user_status = user.split("def _render_runner_status", 1)[1].split(
            "def _failed_run_id", 1
        )[0]
        self.assertIn("if terminal:", user_status)
        self.assertIn("self.progress_sources.clear()", user_status)

    def test_confirmed_safe_recovery_outcomes_are_green(self):
        flow = self.enduser.split("if terminal:", 1)[1].split(
            "def _finalize_success_flow", 1
        )[0]
        self.assertIn('elif result_type == "recovery-completed":', flow)
        self.assertIn(
            '"runner-recovery-user", "ok"',
            flow,
        )
        self.assertIn(
            '"runner-terminal-user", "ok"',
            flow,
        )
        self.assertIn('elif result_type == "aborted-before-transfer":', flow)
        aborted = flow.split('elif result_type == "aborted-before-transfer":', 1)[1].split(
            'elif result_type in {"recovery-required", "reboot-detected"}:', 1
        )[0]
        self.assertIn('"runner-terminal-user", "ok"', aborted)
        self.assertNotIn('"runner-terminal-user", "warn"', aborted)

    def test_verified_service_restart_is_presented_as_completed(self):
        method = self.product.split("def _render_runner_status", 1)[1].split("def _update_debug_line", 1)[0]
        self.assertIn('status.get("service_restart_requested") is True', method)
        self.assertIn('status.get("service_restart_verified") is True', method)

    def test_product_moves_status_button_to_protocol_toolbar(self):
        ui = self.product.split("def _ui(self):", 1)[1].split("# ------------------------------------------------------------------\n    # Final maintenance UI", 1)[0]
        self.assertIn("source_layout.removeWidget(self.ota_reattach_btn)", ui)
        self.assertIn("log_toolbar.insertWidget", ui)

    def test_product_places_manifest_immediately_before_advanced(self):
        ui = self.product.split("def _ui(self):", 1)[1].split("# ------------------------------------------------------------------\n    # Final maintenance UI", 1)[0]
        self.assertIn("manifest_index = next(", ui)
        self.assertIn("advanced_index = next(", ui)
        self.assertIn("self.tabs.insertTab(advanced_index, manifest_widget, manifest_text)", ui)


if __name__ == "__main__":
    unittest.main()
