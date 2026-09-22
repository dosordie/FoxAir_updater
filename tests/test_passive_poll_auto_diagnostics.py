from __future__ import annotations

import unittest
from pathlib import Path

from updater.dtu_ota.cli import build_parser


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_GUI = ROOT / "updater/windows/foxair_updater_release_runtime.py"
BUILD_SCRIPT = ROOT / "updater/windows/build_windows_portable.bat"


class PassivePollAndAutoDiagnosticsTests(unittest.TestCase):
    def test_status_cli_supports_read_only_no_reconcile_mode(self):
        args = build_parser().parse_args(
            ["status", "--run-id", "run-42", "--no-reconcile"]
        )
        self.assertEqual(args.command, "status")
        self.assertEqual(args.run_id, "run-42")
        self.assertTrue(args.no_reconcile)

    def test_release_runtime_uses_passive_poll_and_stale_reconcile(self):
        source = RUNTIME_GUI.read_text(encoding="utf-8")
        compile(source, str(RUNTIME_GUI), "exec")
        self.assertIn("PASSIVE_STATUS_STALE_SECONDS = 10.0", source)
        self.assertIn('args.append("--no-reconcile")', source)
        self.assertIn("_passive_status_same_since", source)
        self.assertIn("_passive_last_reconcile_at", source)
        self.assertIn("RECONCILE_RETRY_SECONDS = 10.0", source)

    def test_failure_and_success_states_are_automatically_archived(self):
        source = RUNTIME_GUI.read_text(encoding="utf-8")
        self.assertIn('recovery == "required"', source)
        self.assertIn('terminal and result_type in AUTO_CLEANUP_RESULTS', source)
        self.assertIn('self._run("runner-auto-diagnostics"', source)

    def test_windows_build_uses_final_runtime_layer(self):
        source = BUILD_SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            r"updater\windows\foxair_updater_release_runtime.py",
            source,
        )
        self.assertNotIn(
            r"updater\windows\foxair_updater_release_product.py || goto :err",
            source,
        )


if __name__ == "__main__":
    unittest.main()
