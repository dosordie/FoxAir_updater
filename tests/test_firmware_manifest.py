import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from updater.common.firmware_manifest import FirmwareManifest, ManifestError


class FirmwareManifestTests(unittest.TestCase):
    def make(self, directory: Path):
        firmware = directory / "FW3.4.bin"
        firmware.write_bytes(b"firmware-3.4")
        value = {
            "schema": "foxair-firmware-v1", "firmware_file": firmware.name,
            "software_code": "82400644", "display_version": "V3.4",
            "wire_version": "0034", "target_ssid": "0063",
            "size": firmware.stat().st_size,
            "md5": hashlib.md5(firmware.read_bytes()).hexdigest().upper(),
            "sha256": hashlib.sha256(firmware.read_bytes()).hexdigest().upper(),
            "image_base": "0x08050000",
        }
        path = directory / "FW3.4.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path, firmware

    def test_loads_and_validates_matching_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path, firmware = self.make(Path(temp))
            manifest = FirmwareManifest.load(path)
            manifest.validate_file(manifest.resolve_firmware(path))
            self.assertEqual(manifest.wire_version, "0034")
            self.assertEqual(manifest.resolve_firmware(path), firmware)

    def test_rejects_version_mismatch_and_modified_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            path, firmware = self.make(Path(temp))
            value = json.loads(path.read_text())
            value["wire_version"] = "0033"
            path.write_text(json.dumps(value))
            with self.assertRaises(ManifestError):
                FirmwareManifest.load(path)
            path, firmware = self.make(Path(temp))
            manifest = FirmwareManifest.load(path)
            firmware.write_bytes(b"changed")
            with self.assertRaises(ManifestError):
                manifest.validate_file(firmware)

    def test_rejects_firmware_larger_than_c357_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            path, _ = self.make(Path(temp))
            value = json.loads(path.read_text())
            value["size"] = 0x4B000 + 1
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ManifestError, "C357 limit"):
                FirmwareManifest.load(path)


if __name__ == "__main__":
    unittest.main()
