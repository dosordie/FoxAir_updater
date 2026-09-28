import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ControllerFreeProductTests(unittest.TestCase):
    def test_linux_launcher_uses_only_autonomous_runner_and_shared_restore(self):
        launcher = Path("foxair-updater").read_text(encoding="utf-8")
        update = launcher.split("    update)", 1)[1].split("    restore)", 1)[0]
        restore = launcher.split("    restore)", 1)[1].split("    download)", 1)[0]
        self.assertIn('python3 "$AUTONOMOUS"', update)
        self.assertIn('full_manifest_preflight "$manifest"', update)
        self.assertIn('python3 "$ORIGINAL_STATE"', restore)
        self.assertNotIn("phnix_local_ota_controller", launcher)
        self.assertNotIn("CACHE_PENDING", launcher)
        self.assertNotIn("same-version)", launcher)

    def test_windows_product_has_no_legacy_controller_wiring(self):
        base = Path("updater/windows/foxair_updater_gui.py").read_text(encoding="utf-8")
        desktop = Path("updater/windows/foxair_updater_desktop.py").read_text(encoding="utf-8")
        product = Path("updater/windows/foxair_updater_release_product.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("phnix_local_ota_controller", base)
        self.assertNotIn("self.controller", base)
        self.assertNotIn("cache.pending", desktop)
        self.assertNotIn("phnix_windows_controller_wrapper", desktop)
        self.assertIn("_original_state_core()", product)

    def test_windows_packaging_contains_runner_and_original_state_not_legacy_controller(self):
        prepare = Path("updater/windows/prepare_windows_backend.py").read_text(
            encoding="utf-8"
        )
        verify = Path("updater/windows/verify_windows_backend.py").read_text(
            encoding="utf-8"
        )
        build = Path("updater/windows/build_windows_portable.bat").read_text(
            encoding="utf-8"
        )
        combined = prepare + verify + build
        self.assertIn("original_state.py", combined)
        self.assertIn("updater/dtu_ota", combined)
        for legacy in (
            "phnix_local_ota_controller.py",
            "phnix_local_ota_controller_hardened.py",
            "phnix_windows_controller_wrapper.py",
            "phnix_windows_restore_grace_wrapper.py",
        ):
            self.assertNotIn(legacy, combined)

    def test_legacy_product_files_are_removed(self):
        for path in (
            "tools/phnix_ota/phnix_local_ota_controller.py",
            "tools/phnix_ota/phnix_local_ota_controller_hardened.py",
            "updater/windows/phnix_windows_controller_wrapper.py",
            "updater/windows/phnix_windows_restore_grace_wrapper.py",
            "updater/windows/prepare_legacy_restore_hook.py",
        ):
            self.assertFalse(Path(path).exists(), path)


    def test_windows_backend_can_be_prepared_without_legacy_controller(self):
        with tempfile.TemporaryDirectory() as temp:
            completed = subprocess.run(
                [
                    sys.executable,
                    "updater/windows/prepare_windows_backend.py",
                    "--root",
                    ".",
                    "--out",
                    temp,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            backend = Path(temp) / "backend"
            for path in (
                backend / "updater/dtu_ota/cli.py",
                backend / "updater/dtu_ota/original_state.py",
                backend / "updater/dtu_ota/payload/phnix_ota_runtime_hook",
                backend / "tools/phnix_ota/create_firmware_manifest.py",
            ):
                self.assertTrue(path.is_file(), path)
            legacy_names = {
                "phnix_local_ota_controller.py",
                "phnix_local_ota_controller_hardened.py",
                "phnix_windows_controller_wrapper_core.py",
            }
            self.assertFalse(
                any(path.name in legacy_names for path in backend.rglob("*") if path.is_file())
            )


if __name__ == "__main__":
    unittest.main()
