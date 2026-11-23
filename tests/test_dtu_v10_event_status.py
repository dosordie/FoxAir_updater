"""V1.0 supervisor diagnostics: C36E sequence and fail-closed restart invariants."""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SUPERVISOR = Path(__file__).resolve().parents[1] / "updater/dtu_ota/payload/dtu_ota_supervisor_v10.sh"


class V10SupervisorDiagnosticsTests(unittest.TestCase):
    @staticmethod
    def _extract_c36e_function() -> str:
        source = SUPERVISOR.read_text(encoding="utf-8")
        start = "refresh_c36e_events() {\n"
        end = "\nrefresh_progress() {"
        assert source.count(start) == source.count(end) == 1
        return start + source.split(start, 1)[1].split(end, 1)[0]

    @unittest.skipUnless(shutil.which("sh") and os.name != "nt", "POSIX shell required")
    def test_c36e_sequence_duplicates_and_repeated_poll(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "gdb.log").write_text(
                "PHNIX first-c36e pc=0x1b434 ssid=0x63 status=1\n"
                "PHNIX later-c36e status=2\n"
                "PHNIX later-c36e status=3\n"
                "PHNIX later-c36e status=3\n"
                "PHNIX later-c36e status=5\n",
                encoding="utf-8",
            )
            events = root / "events.log"
            script = (
                f"HOOK_RUNTIME={shlex.quote(str(root))}\n"
                f"C36E_EVENTS_FILE={shlex.quote(str(events))}\n"
                "C36E_EVENT_COUNT=0\n"
                "C36E_INITIAL_STATUS=0\n"
                "C36E_LAST_STATUS=0\n"
                "C36E_DUPLICATE_COUNT=0\n"
                "C36E_SEEN=false\n"
                "C36E_STATUS=0\n"
                + self._extract_c36e_function()
                + "\nrefresh_c36e_events\n"
                + 'printf "%s:%s:%s:%s:%s\\n" "$C36E_INITIAL_STATUS" "$C36E_LAST_STATUS" "$C36E_EVENT_COUNT" "$C36E_DUPLICATE_COUNT" "$C36E_STATUS"\n'
                + "refresh_c36e_events\n"
                + 'printf "after=%s\\n" "$C36E_EVENT_COUNT"\n'
            )
            result = subprocess.run(["sh", "-c", script], text=True, capture_output=True, check=True)
            self.assertIn("1:5:5:1:5", result.stdout)
            self.assertIn("after=5", result.stdout)
            rows = events.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 5)
            self.assertIn("status=3", rows[3])
            self.assertIn("status=5", rows[4])

    def test_restart_keeps_singleton_and_tracer_guard(self):
        text = SUPERVISOR.read_text(encoding="utf-8")
        restart = text.split("restart_service() {", 1)[1].split("\nstart_service_direct() {", 1)[0]
        self.assertIn('test "$current_count" = 1', restart)
        self.assertIn('test "$stable_count" -ge 10', restart)
        self.assertIn("TracerPid:", restart)
        self.assertIn('test "$is_old" = false && test "$old_alive" = false', restart)
        self.assertIn('SERVICE_RESTART_TIMEOUT=120', text)
        self.assertIn("service_restart_failed", text)
        self.assertIn("controlled restart observation", restart)

    def test_only_v10_supervisor_uses_extended_c36e_fields(self):
        text = SUPERVISOR.read_text(encoding="utf-8")
        for key in (
            "c36e_initial_status", "c36e_last_status",
            "c36e_event_count", "c36e_duplicate_count",
        ):
            self.assertIn(f'"{key}"', text)


if __name__ == "__main__":
    unittest.main()
