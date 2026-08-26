import json
import unittest

from updater.common.phnix_traffic import EventRing, mask_secret, parse_gdb_trace, sanitize_fields


class TrafficTest(unittest.TestCase):
    def test_secret_masking_contract(self):
        self.assertEqual(mask_secret(""), "nicht gesetzt")
        self.assertEqual(mask_secret("abcd"), "****")
        self.assertEqual(mask_secret("abcdefgh"), "****efgh")
        self.assertEqual(sanitize_fields({"deviceSecret": "abcdefgh"})["deviceSecret"], "****efgh")

    def test_trace_parser_rejects_bad_lengths(self):
        data = parse_gdb_trace("FOX|mqtt|tx|user/update|2|0x1234|63 10 \nFOX|mqtt|rx|ota|3|0x1|00")
        rows = data.splitlines()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0])["payload_hex"], "63 10")

    def test_ring_is_bounded_and_redacts_json(self):
        ring = EventRing(2)
        for number in range(3):
            ring.add_json_lines(json.dumps({
                "protocol": "https", "direction": "rx", "channel": "register",
                "length": 1, "payload_type": "json", "sensitive": True,
                "payload_text": json.dumps({"deviceSecret": "abcdefgh", "code": number}),
            }))
        self.assertEqual(len(ring.snapshot()), 2)
        self.assertIn("****efgh", ring.snapshot()[-1].payload_text)


if __name__ == "__main__":
    unittest.main()
