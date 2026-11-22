"""V1.0 offline ELF-signature checks; production OTA is never enabled."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from devtools.phnix_ota_v10.verify_static import DEFAULT_SITES, inspect
from updater.dtu_ota.build_profiles import V10


class V10StaticCheckerTests(unittest.TestCase):
    def test_candidate_manifest_is_pinned_and_has_18_unique_sites(self):
        manifest = json.loads(DEFAULT_SITES.read_text(encoding="utf-8"))
        self.assertEqual(manifest["source_sha256"], V10.service_sha256)
        self.assertEqual(manifest["build_id"], V10.elf_build_id)
        entries = manifest["entries"]
        self.assertEqual(len(entries), 18)
        self.assertEqual(len({entry["name"] for entry in entries}), 18)
        self.assertEqual(len({entry["v10_candidate"] for entry in entries}), 18)
        for entry in entries:
            address = int(entry["v10_candidate"], 16)
            self.assertEqual(address % 4, 0)
            self.assertEqual(len(bytes.fromhex(entry["v10_machine_bytes_8"])), 8)

    def test_foreign_binary_is_rejected_without_reading_elf_data(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "phnixIot4G"
            path.write_bytes(b"not an ELF")
            result = inspect(path)
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "foreign-binary")

    def test_tampered_candidate_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "phnixIot4G"
            binary.write_bytes(b"invalid")
            sites = root / "manifest.json"
            data = json.loads(DEFAULT_SITES.read_text(encoding="utf-8"))
            data["source_sha256"] = "0" * 64
            sites.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match pinned"):
                inspect(binary, sites)

    @unittest.skipUnless(
        os.environ.get("FOXAIR_DTU_V10_LOCAL_BINARY"),
        "Requires locally supplied original binary; never commit firmware to repo",
    )
    def test_optional_real_original_elf(self):
        result = inspect(Path(os.environ["FOXAIR_DTU_V10_LOCAL_BINARY"]))
        self.assertTrue(result["ok"])
        self.assertFalse(result["ota_authorized"])
        self.assertEqual(result["signatures_ok"], 18)


if __name__ == "__main__":
    unittest.main()
