import json
import unittest
from unittest.mock import patch

from pathlib import Path

from updater.common.phnix_traffic import (
    EventRing, TrafficTracer, export_events, mask_secret, parse_gdb_trace, sanitize_fields,
)


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
        self.assertIsNone(ring.snapshot()[-1].payload_text)
        self.assertNotIn("abcdefgh", export_events(ring.snapshot()))

    def test_every_ui_channel_has_a_parser_and_hook_fixture(self):
        raw = "\n".join((
            "FOX|mqtt|tx|user/update|2|0x1|63 10 ",
            "FOX|mqtt|rx|user/get|1|0x1|03 ",
            "FOX|mqtt|rx|ota|1|0x1|7b ",
            "FOX|mqtt|tx|ota_update|1|0x1|7d ",
            "META|ota_start|mainboard|/cache/phnixIot_device_OTA|https://example/fw.bin",
            "FOX|http|rx|ota_chunk|4096|0x1|",
            "META|provision|linked_go_queryiotdevice|http|120",
            "META|provision|legacy_queryiotdevice|http|80",
            "META|provision|linked_go_create_device_by_sign|http|0",
            "META|provision|aliyun_dynamic_register|https|0",
            "META|provision|aliyun_dynamic_register_response|https|0",
        ))
        channels = {json.loads(line)["channel"] for line in parse_gdb_trace(raw).splitlines()}
        self.assertEqual(channels, {"user/update", "user/get", "ota", "ota_update",
                                    "ota_download_start", "ota_chunk",
                                    "linked_go_queryiotdevice", "legacy_queryiotdevice",
                                    "linked_go_create_device_by_sign", "aliyun_dynamic_register",
                                    "aliyun_dynamic_register_response"})
        hook = Path("tools/phnix_traffic/foxair_traffic_trace").read_text(encoding="utf-8")
        for address in ("0x1F6FC", "0x1EED0", "0x1ED98", "0x1F9B0", "0x19A54",
                        "0x19E70", "0x19C18", "0x16960", "0x15C58", "0x164AC",
                        "0x22FF4", "0x22B9C"):
            self.assertIn(f"break *{address}", hook)

    def test_all_secret_spellings_are_removed_from_ring_and_export(self):
        secrets = {"DeviceSecret": "device-raw-secret", "ProductSecret": "product-raw-secret",
                   "sign": "raw-signature"}
        ring = EventRing()
        ring.add_json_lines(json.dumps({"protocol": "https", "direction": "rx",
            "channel": "aliyun_dynamic_register_response", "length": 12,
            "payload_type": "json", "payload_hex": "72 61 77", "payload_text": json.dumps(secrets),
            "fields": secrets, "sensitive": True}))
        exported = export_events(ring.snapshot())
        for raw in secrets.values():
            self.assertNotIn(raw, exported)
        self.assertNotIn("72 61 77", exported)

    def test_ota_download_metadata_and_dtu_target(self):
        rows = parse_gdb_trace("META|ota_start|dtu|/data/phnixIot4G_OTA|http://example/dtu")
        event = json.loads(rows)
        self.assertEqual(event["fields"]["download_type"], "dtu")
        self.assertEqual(event["fields"]["target"], "/data/phnixIot4G_OTA")

    def test_remote_log_is_read_incrementally_and_keeps_partial_line(self):
        class FakeAdb:
            def __init__(self):
                self.calls = []
                self.responses = [
                    "FOXAIR_SIZE:32\nFOX|mqtt|tx|user/update|1|0x1|",
                    "FOXAIR_SIZE:36\n63 \n",
                ]

            def run(self, *args):
                self.calls.append(args)
                return self.responses.pop(0)

        adb = FakeAdb()
        tracer = TrafficTracer(adb, "unused")
        self.assertEqual(tracer.events(), "")
        parsed = tracer.events()
        self.assertEqual(json.loads(parsed)["payload_hex"], "63")
        self.assertIn("skip=0", adb.calls[0][1])
        self.assertIn("skip=32", adb.calls[1][1])

    def test_enable_hashes_bytes_from_adb_client_before_installing_helper(self):
        class FakeAdb:
            def __init__(self):
                self.pushed = False
                self.commands = []

            def read_file(self, remote):
                self.commands.append(("read_file", remote))
                return b"verified binary"

            def push(self, *args):
                self.pushed = True

            def shell(self, command):
                self.commands.append(((command,), {}))
                return "active"

        expected = __import__("hashlib").sha256(b"verified binary").hexdigest()
        adb = FakeAdb()
        with patch("updater.common.phnix_traffic.EXPECTED_SERVICE_SHA256", expected):
            self.assertEqual(TrafficTracer(adb, "helper").enable(), "active")
        self.assertEqual(adb.commands[0], ("read_file", "/data/phnixIot4G"))
        self.assertTrue(adb.pushed)
        self.assertIn("start --sha256 " + expected, adb.commands[1][0][0])

    def test_unknown_binary_is_rejected_before_helper_push(self):
        class FakeAdb:
            def read_file(self, remote): return b"unknown"
            def push(self, *args): raise AssertionError("helper must not be pushed")

        with self.assertRaisesRegex(RuntimeError, "Nicht unterstützte phnixIot4G-Version"):
            TrafficTracer(FakeAdb(), "helper").enable()

    def test_remote_helper_needs_no_elf_utilities_and_rechecks_before_attach(self):
        hook = Path("tools/phnix_traffic/foxair_traffic_trace").read_text(encoding="utf-8")
        self.assertNotIn("readelf", hook)
        self.assertNotIn("objdump", hook)
        self.assertIn('/bin/sha256sum "$BIN"', hook)
        self.assertIn('readlink "/proc/$CHECK_PID/exe"', hook)
        self.assertIn('kill -0 "$CHECK_PID"', hook)
        self.assertIn('test -r "/proc/$CHECK_PID/maps"', hook)
        verify_calls = hook.count('verify_running_binary "$PID"')
        self.assertEqual(verify_calls, 2)
        self.assertLess(hook.rfind('verify_running_binary "$PID"'),
                        hook.index("gdbserver --attach"))


if __name__ == "__main__":
    unittest.main()
