import unittest
from pathlib import Path


class EmptyUpdateStatusUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path(
            "updater/windows/foxair_updater_runner_user_gui.py"
        ).read_text(encoding="utf-8")

    def test_missing_last_run_is_presented_as_normal_empty_history(self):
        self.assertIn('if op == "runner-current":', self.ui)
        self.assertIn('status.get("error") == "DTU has no last_run_id"', self.ui)
        self.assertIn('runner.legacy.MainWindow._done(self, "handled-result", code, output)', self.ui)

    def test_empty_history_clears_runner_state(self):
        for assignment in (
            "self._runner_run_id = None",
            "self._runner_prepared_manifest = None",
            "self._runner_active = False",
            "self._runner_terminal = False",
            "self._runner_abort_allowed = False",
            "self._runner_acknowledged = False",
        ):
            self.assertIn(assignment, self.ui)


if __name__ == "__main__":
    unittest.main()
