import tempfile
import unittest
from pathlib import Path

from updater.dtu_ota.package import PackageError, shell_payload_bytes


class DtuOtaTerminalRaceTests(unittest.TestCase):
    def test_packaged_supervisor_rechecks_terminal_after_hook_exit(self):
        path = Path("updater/dtu_ota/payload/dtu_ota_supervisor.sh")
        source = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        payload = shell_payload_bytes(path)

        old = (
            b'wait "$HOOK_PID" 2>/dev/null; hook_rc=$?\n'
            b'            if test "$ORIGINAL_AUTH" = true; then\n'
        )
        self.assertIn(old, source)
        self.assertNotIn(old, payload)

        block = payload.split(b'if ! kill -0 "$HOOK_PID" 2>/dev/null; then', 1)[1]
        block = block.split(b'if restore_original_confirmed', 1)[0]
        wait_at = block.index(b'wait "$HOOK_PID" 2>/dev/null; hook_rc=$?')
        reread_at = block.index(b'final_terminal=$(hook_bool terminal)')
        continue_at = block.index(b'continue')
        guard_at = block.index(b'if test "$ORIGINAL_AUTH" = true; then')
        self.assertLess(wait_at, reread_at)
        self.assertLess(reread_at, continue_at)
        self.assertLess(continue_at, guard_at)

    def test_supervisor_patch_fails_closed_if_expected_source_block_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dtu_ota_supervisor.sh"
            path.write_text("#!/system/bin/sh\necho changed\n", encoding="utf-8")
            with self.assertRaisesRegex(PackageError, "expected exactly one source block"):
                shell_payload_bytes(path)


if __name__ == "__main__":
    unittest.main()
