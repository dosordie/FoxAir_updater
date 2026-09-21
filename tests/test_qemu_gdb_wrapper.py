"""VM-only GDB adapter regression tests."""

import unittest
from pathlib import Path

from tools.testvm.fake_adb.qemu_gdb_wrapper import patch_script


class QemuGdbWrapperTests(unittest.TestCase):
    def test_converts_only_parser_handoff_breakpoints(self):
        source = """file /data/phnixIot4G
target remote 127.0.0.1:12345
break *0x1fe40
break *0x1ba04
break *0x1cea0
printf \"PHNIX yield pc=0x%x\\n\", $pc
"""
        patched, changed = patch_script(source)
        self.assertTrue(changed)
        self.assertIn("hbreak *0x1fe40", patched)
        self.assertIn("hbreak *0x1ba04", patched)
        self.assertIn("break *0x1cea0", patched)

    def test_ignores_unrelated_gdb_script(self):
        source = "target remote 127.0.0.1:12345\nbreak *0x1fe40\n"
        patched, changed = patch_script(source)
        self.assertFalse(changed)
        self.assertEqual(patched, source)

    def test_wrapper_overlay_is_after_root_bind_and_before_command(self):
        # Source-level guard: a file overlay inserted before `--bind / /`
        # would be hidden again by that later root mount.
        source = (
            Path(__file__).resolve().parents[1]
            / "tools/testvm/fake_adb/qemu_permissive_backend.py"
        ).read_text(encoding="utf-8")
        self.assertIn('separator = argv.index("--")', source)
        self.assertIn('argv[separator:separator] = [', source)


if __name__ == "__main__":
    unittest.main()
