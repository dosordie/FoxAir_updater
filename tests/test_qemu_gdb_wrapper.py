"""VM-only GDB adapter regression tests."""

import unittest
from pathlib import Path

from tools.testvm.fake_adb.qemu_gdb_wrapper import patch_script


class QemuGdbWrapperTests(unittest.TestCase):
    def test_converts_only_parser_handoff_breakpoints(self):
        source = """file /data/phnixIot4G
target remote 127.0.0.1:12345
break *0x1fe40
thbreak *0x1c4bc
commands 2
  silent
  printf \"PHNIX post-parser pc=0x%x\\n\", $pc
  continue
end
break *0x1ba04
commands 1
  silent
  printf \"PHNIX yield pc=0x%x\\n\", $pc
  disable 1
  set $return_pc = $pc
  continue
end
break *0x1cea0
continue
printf "PHNIX first-c36e pc=0x%x ssid=0x%x status=%u\\n", $pc, *(unsigned char *)($r0+1), *(unsigned char *)($r0+3)
"""
        patched, changed = patch_script(source)
        self.assertTrue(changed)
        self.assertIn("thbreak *0x1fe40", patched)
        self.assertIn("hbreak *0x1ba04", patched)
        self.assertNotIn("disable 1", patched)
        self.assertIn("break *0x1cea0", patched)
        self.assertNotIn("file /data/phnixIot4G", patched)
        self.assertIn("  hbreak *0x9a98", patched)
        self.assertIn("while $pc == 0x9a98", patched)
        self.assertIn("set $r0 = 0", patched)
        self.assertIn("set $pc = $lr", patched)
        self.assertIn("disable 4", patched)
        self.assertIn("shell rm -f /cache/phnixIot_device_OTA", patched)
        self.assertIn("shell : > /data/phnixIot_device_OTA_INFO", patched)

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
