import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock

from tools.phnix_ota import phnix_local_ota_controller_hardened as hardened


class OtaHardeningTests(unittest.TestCase):
    def test_df_parser_ignores_header_and_uses_last_valid_data_row(self):
        output = (
            "Filesystem 1K-blocks Used Available Use% Mounted on\n"
            "sim 1048576 1 1048575 1% /data\n"
        )
        result = hardened.parse_df_output(output, "/data")
        self.assertEqual(result["filesystem"], "sim")
        self.assertEqual(result["free_bytes"], 1048575 * 1024)

    def test_df_parser_fails_closed_without_numeric_data_row(self):
        with self.assertRaises(hardened.core.OtaError):
            hardened.parse_df_output(
                "Filesystem 1K-blocks Used Available Use% Mounted on\n",
                "/data",
            )

    def test_remote_df_is_parsed_on_host_without_tail_pipeline(self):
        adb = Mock()
        adb.shell.return_value = (
            "Filesystem 1K-blocks Used Available Use% Mounted on\n"
            "sim 1048576 1 1048575 1% /data\n"
        )
        result = hardened.remote_filesystem_stat(adb, "/data")
        adb.shell.assert_called_once_with("df -k /data 2>/dev/null")
        self.assertEqual(result["filesystem"], "sim")

    def test_same_filesystem_storage_requires_two_firmware_copies_plus_margin(self):
        adb = Mock()
        adb.shell.side_effect = [
            "/dev/root 10000 1000 5000 20% /data",
            "/dev/root 10000 1000 5000 20% /cache",
        ]
        manifest = Mock(size=300_000)
        checks = {"ok": True, "failures": []}
        result = hardened.add_storage_preflight(checks, adb, manifest)
        expected = 2 * 300_000 + hardened.STORAGE_SAFETY_MARGIN_BYTES
        self.assertTrue(result["storage_preflight"]["ok"])
        requirement = result["storage_preflight"]["requirements"]["/dev/root"]
        self.assertEqual(requirement["required_bytes"], expected)
        self.assertEqual(requirement["paths"], ["/data", "/cache"])

    def test_storage_preflight_fails_closed_when_space_is_too_small(self):
        adb = Mock()
        adb.shell.side_effect = [
            "/dev/data 10000 9000 200 90% /data",
            "/dev/cache 10000 1000 5000 20% /cache",
        ]
        manifest = Mock(size=300_000)
        result = hardened.add_storage_preflight({"ok": True, "failures": []}, adb, manifest)
        self.assertFalse(result["ok"])
        self.assertTrue(any("insufficient free storage" in item for item in result["failures"]))

    def test_host_run_state_is_cross_platform_pathlib_json_and_preserves_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "20260824-193600" / "run-state.json"
            hardened.write_host_run_state(
                path,
                phase="prepared",
                transfer_started=False,
                point_of_no_return=False,
            )
            hardened.write_host_run_state(
                path,
                phase="c5a8",
                transfer_started=True,
                point_of_no_return=True,
                highest_confirmed_offset=168,
            )
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(value["schema"], "foxair-ota-run-state-v1")
            self.assertEqual(value["phase"], "c5a8")
            self.assertTrue(value["transfer_started"])
            self.assertTrue(value["point_of_no_return"])
            self.assertEqual(value["highest_confirmed_offset"], 168)
            self.assertIn("updated_at", value)
            self.assertFalse(path.with_name("run-state.json.tmp").exists())

    def test_transfer_complete_message_distinguishes_transport_from_final_completion(self):
        hardened.core.COLOR_ENABLED = False
        output = io.StringIO()
        with redirect_stdout(output):
            hardened._patched_human_event(
                "transfer-complete",
                {"offset": 287_598, "length": 287_598},
            )
        rendered = output.getvalue()
        self.assertIn("100 % Firmware uebertragen", rendered)
        self.assertIn("intern noch programmieren und verifizieren", rendered)

    def test_pr1_does_not_replace_the_core_ota_lifecycle(self):
        source = Path("tools/phnix_ota/phnix_local_ota_controller_hardened.py").read_text(encoding="utf-8")
        self.assertIn("_ORIGINAL_RUN_UPDATE = core.run_update", source)
        self.assertIn("return _ORIGINAL_RUN_UPDATE(args, adb)", source)
        self.assertNotIn("REMOTE_HELPER} hold", source)
        self.assertNotIn("host-supervision-lost", source)
        self.assertNotIn("transfer-unattended", source)

    def test_runtime_hook_keeps_original_guarded_hold_semantics_in_pr1(self):
        hook = Path("updater/dtu_ota/payload/phnix_ota_runtime_hook").read_text(encoding="utf-8")
        cleanup = hook.split("cleanup() {", 1)[1].split("stop_hook() {", 1)[0]
        self.assertIn("kill -STOP", cleanup)
        self.assertNotIn("transfer-unattended", cleanup)

    def test_linux_launcher_requires_full_for_real_update(self):
        launcher = Path("foxair-updater").read_text(encoding="utf-8")
        update = launcher.split("    update)", 1)[1].split("    same-version)", 1)[0]
        self.assertIn("Echte Updates benoetigen zwingend --full", update)
        self.assertIn('full_manifest_preflight "$manifest"', update)
        self.assertIn('if [[ "$phase" == "same-version" ]]', update)
        self.assertIn("restore_update_cache", update)

    def test_windows_wrapper_uses_stable_ota_state_and_same_version_cache_restore(self):
        wrapper = Path("updater/windows/phnix_windows_controller_wrapper.py").read_text(encoding="utf-8")
        self.assertIn('windows_app_state_root() / "ota-state"', wrapper)
        self.assertIn("phnix_local_ota_controller_hardened.py", wrapper)
        full = wrapper.split("if is_full_update:", 1)[1].split("if is_same:", 1)[0]
        self.assertIn('if phase == "same-version":', full)
        self.assertIn("restore_update_cache(base)", full)
        self.assertIn('elif phase == "success":', full)
        self.assertIn("clear_cache_pending()", full)

    def test_windows_source_mode_uses_repo_root_and_shared_safety_layer(self):
        base_gui = Path("updater/windows/foxair_updater_gui.py").read_text(encoding="utf-8")
        self.assertFalse(Path("backend").exists())
        self.assertIn('packaged = root_dir() / "backend"', base_gui)
        self.assertIn("return packaged if packaged.is_dir() else root_dir()", base_gui)
        self.assertTrue(Path("updater/windows/phnix_windows_controller_wrapper.py").is_file())
        self.assertTrue(Path("tools/phnix_ota/phnix_local_ota_controller_hardened.py").is_file())
        self.assertTrue(Path("tools/phnix_ota/create_firmware_manifest.py").is_file())


if __name__ == "__main__":
    unittest.main()
