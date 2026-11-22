"""Checks for the separate experimental V1.0 runtime payload."""
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "updater/dtu_ota/payload"


class V10PayloadTests(unittest.TestCase):
    def test_hook_uses_candidate_sites_and_byte_uart(self):
        hook = (PAYLOAD / "phnix_ota_runtime_hook_v10").read_text()
        sites = json.loads((ROOT / "devtools/phnix_ota_v10/v10_hook_sites_candidates.json").read_text())
        for site in sites["entries"]:
            self.assertNotIn(site["v12"], hook.lower())
        for address in ("0x1f44c", "0x193f8", "0x1be6c", "0x1b434",
                        "0x1c898", "0x1c164", "0xa2160", "0x1292fc"):
            self.assertIn(address, hook.lower())
        self.assertIn("*(unsigned char *)0xa0728", hook)
        self.assertNotIn("*(unsigned int *)0xa0728", hook)
        self.assertNotIn("phnixIot_device_statisic", hook)
        self.assertNotIn("0x988fe", hook)
        self.assertNotIn("cancel-probe) cancel_probe_hook", hook)

    def test_v12_hook_retains_validated_bytes(self):
        # This commit adds a second hook without editing the original file.
        source = (PAYLOAD / "phnix_ota_runtime_hook").read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),
                         V12_HOOK_SHA256)


V12_HOOK_SHA256 = "c11934d3e11be833558af82c50314776410ba57407c76e9207fd451cb774953e"
