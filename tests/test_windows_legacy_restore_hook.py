import tempfile
import unittest
from pathlib import Path

from updater.windows.prepare_legacy_restore_hook import (
    LEGACY_HEADER,
    legacy_hook_bytes,
    prepare,
)


class WindowsLegacyRestoreHookTests(unittest.TestCase):
    def test_current_bin_sh_hook_is_preserved_with_lf(self):
        raw = b"#!/bin/sh\nset -eu\necho ok\n"
        self.assertEqual(legacy_hook_bytes(raw), raw)

    def test_windows_crlf_checkout_is_normalized(self):
        raw = b"#!/bin/sh\r\nset -eu\r\necho ok\r\n"
        expected = b"#!/bin/sh\nset -eu\necho ok\n"
        self.assertEqual(legacy_hook_bytes(raw), expected)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "runtime_hook"
            output = root / "legacy_hook"
            source.write_bytes(raw)
            prepare(source, output)
            written = output.read_bytes()
            self.assertEqual(written, expected)
            self.assertTrue(written.startswith(LEGACY_HEADER))
            self.assertNotIn(b"\r", written)

    def test_system_bin_sh_variant_is_supported_without_body_change(self):
        raw = b"#!/system/bin/sh\r\nset -eu\r\necho ok\r\n"
        self.assertEqual(
            legacy_hook_bytes(raw),
            b"#!/bin/sh\nset -eu\necho ok\n",
        )

    def test_unexpected_header_fails_closed(self):
        with self.assertRaises(RuntimeError):
            legacy_hook_bytes(b"echo no-shebang\r\n")


if __name__ == "__main__":
    unittest.main()
