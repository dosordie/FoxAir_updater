import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock

from tools.phnix_ota import phnix_local_ota_controller_hardened as hardened


class OtaHardeningTests(unittest.TestCase):
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

    def test_transfer_complete_message_distinguishes_transport_from_promotion(self):
        hardened.core.COLOR_ENABLED = False
        output = io.StringIO()
        with redirect_stdout(output):
            hardened._patched_human_event(
                "transfer-complete",
                {"offset": 287_598, "length": 287_598},
            )
        rendered = output.getvalue()
        self.assertIn("100 % Firmware uebertragen", rendered)
        self.assertIn("programmiert und verifiziert intern weiter", rendered)

    def test_runtime_hook_cleanup_never_sigstops_after_transfer_started(self):
        hook = Path("tools/phnix_ota/phnix_ota_runtime_hook").read_text(encoding="utf-8")
        cleanup = hook.split("cleanup() {", 1)[1].split("stop_hook() {", 1)[0]
        post_transfer = cleanup.split('if test -f "$TRANSFER_STARTED"; then', 1)[1].split("\n        fi", 1)[0]
        self.assertIn("transfer-unattended", post_transfer)
        self.assertIn("return", post_transfer)
        self.assertNotIn("kill -STOP", post_transfer)
        self.assertIn("kill -STOP", cleanup)

    def test_hardened_host_exception_has_no_hold_after_point_of_no_return(self):
        source = Path("tools/phnix_ota/phnix_local_ota_controller_hardened.py").read_text(encoding="utf-8")
        exception = source.split("except BaseException as error:", 1)[1].split("\n    finally:", 1)[0]
        started_branch = exception.split("if started:", 1)[1].split("\n            else:", 1)[0]
        pre_transfer_branch = exception.split("\n            else:", 1)[1]
        self.assertIn("host-supervision-lost", started_branch)
        self.assertNotIn(" hold --status ", started_branch)
        self.assertIn(" hold --status ", pre_transfer_branch)

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
        self.assertIn('core = here / "phnix_local_ota_controller_hardened.py"', wrapper)
        full = wrapper.split("if is_full_update:", 1)[1].split("if is_same:", 1)[0]
        self.assertIn('if phase == "same-version":', full)
        self.assertIn("restore_update_cache(base)", full)
        self.assertIn('elif phase == "success":', full)
        self.assertIn("clear_cache_pending()", full)


if __name__ == "__main__":
    unittest.main()
