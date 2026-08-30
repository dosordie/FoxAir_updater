import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from updater.windows import phnix_windows_controller_wrapper as wrapper


class WindowsWrapperStateTests(unittest.TestCase):
    def test_success_cleanup_removes_only_local_pending_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pending = root / "cache.pending"
            backup = root / "phnixIot_device_OTA"
            pending.touch()
            backup.write_bytes(b"existing backup")
            with patch.object(
                wrapper,
                "cache_paths",
                return_value={"pending": pending, "backup": backup},
            ):
                wrapper.clear_cache_pending()
            self.assertFalse(pending.exists())
            self.assertEqual(backup.read_bytes(), b"existing backup")

    def test_dirty_state_reset_requires_confirmed_pre_transfer_state(self):
        self.assertTrue(wrapper.dirty_state_reset_is_safe({"phase": "c350", "transfer_started": False}))
        self.assertTrue(wrapper.dirty_state_reset_is_safe({"phase": "same-version", "transfer_started": False}))
        self.assertFalse(wrapper.dirty_state_reset_is_safe({"phase": "c5a8", "transfer_started": True}))
        self.assertFalse(wrapper.dirty_state_reset_is_safe({"phase": "c350"}))
        self.assertFalse(wrapper.dirty_state_reset_is_safe(None))

    def test_finished_failed_simulator_run_can_reset_stale_pending_state(self):
        run_state = {"phase": "failed", "terminal": True, "transfer_started": True}
        simulator_state = {
            "marker": "PHNIX-OTA-SIMULATOR-V1",
            "status": {"phase": "failed", "terminal": True},
            "runtime": {"running": False},
        }
        self.assertTrue(wrapper.dirty_state_reset_is_safe(run_state, simulator_state))

    def test_active_or_unclear_c5a8_remains_protected(self):
        run_state = {"phase": "c5a8", "terminal": False, "transfer_started": True}
        simulator_state = {
            "marker": "PHNIX-OTA-SIMULATOR-V1",
            "status": {"phase": "c5a8", "terminal": False},
            "runtime": {"running": True},
        }
        self.assertFalse(wrapper.dirty_state_reset_is_safe(run_state, simulator_state))
        self.assertFalse(wrapper.dirty_state_reset_is_safe(run_state))

    def test_explicit_state_dir_is_the_effective_state_dir(self):
        with tempfile.TemporaryDirectory() as temp:
            wanted = Path(temp) / "gui-state"
            actual = wrapper.update_state_dir(["run", "--state-dir", str(wanted)])
            self.assertEqual(actual, wanted)
            self.assertTrue(wanted.is_dir())

    def test_preexisting_run_state_is_not_reused_as_current_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_dir = root / "20260824-210000"
            old_dir.mkdir()
            (old_dir / "run-state.json").write_text(
                json.dumps({"phase": "same-version"}), encoding="utf-8"
            )
            before = wrapper.snapshot_run_states(root)

            with self.assertRaises(SystemExit) as caught:
                wrapper.latest_update_phase(root, before)
            self.assertEqual(caught.exception.code, 2)

    def test_new_run_state_after_snapshot_is_used(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_dir = root / "20260824-210000"
            old_dir.mkdir()
            (old_dir / "run-state.json").write_text(
                json.dumps({"phase": "same-version"}), encoding="utf-8"
            )
            before = wrapper.snapshot_run_states(root)

            new_dir = root / "20260824-220000"
            new_dir.mkdir()
            (new_dir / "run-state.json").write_text(
                json.dumps({"phase": "success"}), encoding="utf-8"
            )

            self.assertEqual(wrapper.latest_update_phase(root, before), "success")

    def test_modified_run_state_after_snapshot_is_used(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "20260824-220000"
            run_dir.mkdir()
            state = run_dir / "run-state.json"
            state.write_text(json.dumps({"phase": "same-version"}), encoding="utf-8")
            before = wrapper.snapshot_run_states(root)

            state.write_text(
                json.dumps({"phase": "success", "changed": True}), encoding="utf-8"
            )
            self.assertEqual(wrapper.latest_update_phase(root, before), "success")


if __name__ == "__main__":
    unittest.main()
