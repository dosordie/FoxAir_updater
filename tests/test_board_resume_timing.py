"""Linux PTY tests: retained board position and unsolicited timeout C544."""
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/testvm/work_lab/rs485_fault_emulator.py"


@unittest.skipUnless(sys.platform.startswith("linux"), "requires Linux PTYs")
class ResumeTimingTests(unittest.TestCase):
    def exercise(self, profile, age, expect_resume):
        import pty
        import tty
        spec = importlib.util.spec_from_file_location("board", SCRIPT)
        board = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(board)
        master, slave = pty.openpty()
        tty.setraw(slave)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            state.write_text(json.dumps({"next_block": 101, "last_block_at": time.time() - age,
                                         "resume_stage": "receiving"}))
            proc = subprocess.Popen([sys.executable, str(SCRIPT), "--peer", os.ttyname(slave),
                "--transcript", str(root / "trace"), "--from-app", str(root / "rx"),
                "--to-app", str(root / "tx"), "--resume-state", str(state),
                "--resume-timing", profile, "--board-version", "0034"])
            try:
                time.sleep(0.15)
                os.write(master, board.DEVICE_INFO_REQUEST)
                self.assertTrue(select.select([master], [], [], 2)[0])
                os.read(master, 4096)
                os.write(master, board.STATUS_HANDSHAKE_REQUEST)
                collected = b""
                deadline = time.monotonic() + 1.5
                while time.monotonic() < deadline:
                    if select.select([master], [], [], 0.1)[0]:
                        collected += os.read(master, 4096)
                self.assertEqual(board.board_software_info_frame("0034") in collected, expect_resume)
                retained = json.loads(state.read_text())
                self.assertEqual(retained["next_block"], 101)
                if expect_resume:
                    self.assertEqual(retained["resume_stage"], "c544-sent")
                    self.assertIn("interblock-timeout", (root / "trace").read_text())
                self.assertIsNone(proc.poll())
            finally:
                proc.terminate()
                proc.wait(timeout=3)
                os.close(master)
                os.close(slave)

    def test_fast_elapsed_pause_sends_c544_after_identity(self):
        self.exercise("fast", 21, True)

    def test_original_does_not_use_fast_deadline(self):
        self.exercise("original", 21, False)

    def test_original_elapsed_deadline_sends_c544(self):
        self.exercise("original", 934, True)


if __name__ == "__main__":
    unittest.main()
