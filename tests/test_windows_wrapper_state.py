import json
import tempfile
import unittest
from pathlib import Path

from updater.windows import phnix_windows_controller_wrapper as wrapper


class WindowsWrapperStateTests(unittest.TestCase):
    def test_dirty_state_reset_requires_confirmed_pre_transfer_state(self):
        self.assertTrue(wrapper.dirty_state_reset_is_safe({"phase": "c350", "transfer_started": False}))
        self.assertTrue(wrapper.dirty_state_reset_is_safe({"phase": "same-version", "transfer_started": False}))
        self.assertFalse(wrapper.dirty_state_reset_is_safe({"phase": "c5a8", "transfer_started": True}))
        self.assertFalse(wrapper.dirty_state_reset_is_safe({"phase": "c350"}))
        self.assertFalse(wrapper.dirty_state_reset_is_safe(None))

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
