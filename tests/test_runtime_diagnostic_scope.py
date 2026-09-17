from __future__ import annotations

import unittest
from pathlib import Path

from updater.dtu_ota.diagnostics_current_run import runtime_files_for_run


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_GUI = ROOT / "updater/windows/foxair_updater_release_runtime.py"


class FakeAdb:
    def __init__(self, *, hook_reached: bool, mtimes: dict[str, int]):
        self.hook_reached = hook_reached
        self.mtimes = mtimes

    def shell(self, command: str, check: bool = True) -> str:
        if "hook.log" in command and "hook-status.json" in command:
            return "YES\n" if self.hook_reached else "NO\n"
        if "stat -c %Y" in command:
            for path, value in self.mtimes.items():
                if f"'{path}'" in command:
                    return f"{value}\n"
            return ""
        return ""


class RuntimeDiagnosticScopeTests(unittest.TestCase):
    def test_release_uses_run_scoped_diagnostic_wrapper(self):
        source = RUNTIME_GUI.read_text(encoding="utf-8")
        self.assertIn("diagnostics_current_run.py", source)

    def test_stale_global_gdb_log_is_excluded(self):
        run_id = "20260917-152601-7600"
        run_dir = f"/data/foxair_ota_runner/runs/{run_id}"
        adb = FakeAdb(
            hook_reached=True,
            mtimes={
                f"{run_dir}/runner.pid": 200,
                "/tmp/phnix_ota_hook/gdb.log": 150,
                "/tmp/phnix_ota_hook/gdbserver.log": 210,
            },
        )
        files = runtime_files_for_run(adb, run_id)
        self.assertNotIn("dtu-state/runtime/gdb.log", files)
        self.assertEqual(
            files.get("dtu-state/runtime/gdbserver.log"),
            "/tmp/phnix_ota_hook/gdbserver.log",
        )

    def test_same_version_or_preflight_run_does_not_inherit_old_logs(self):
        run_id = "20260917-160000-0001"
        run_dir = f"/data/foxair_ota_runner/runs/{run_id}"
        adb = FakeAdb(
            hook_reached=False,
            mtimes={
                f"{run_dir}/runner.pid": 300,
                "/tmp/phnix_ota_hook/gdb.log": 350,
                "/tmp/phnix_ota_hook/gdbserver.log": 350,
            },
        )
        self.assertEqual(runtime_files_for_run(adb, run_id), {})

    def test_current_run_logs_are_included(self):
        run_id = "20260917-170000-0002"
        run_dir = f"/data/foxair_ota_runner/runs/{run_id}"
        adb = FakeAdb(
            hook_reached=True,
            mtimes={
                f"{run_dir}/runner.pid": 400,
                "/tmp/phnix_ota_hook/gdb.log": 405,
                "/tmp/phnix_ota_hook/gdbserver.log": 401,
            },
        )
        files = runtime_files_for_run(adb, run_id)
        self.assertEqual(set(files), {
            "dtu-state/runtime/gdb.log",
            "dtu-state/runtime/gdbserver.log",
        })


if __name__ == "__main__":
    unittest.main()
