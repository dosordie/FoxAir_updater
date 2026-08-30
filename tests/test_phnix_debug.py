import queue
import threading
import time
import unittest
from pathlib import Path

from updater.common.phnix_debug import (
    PhnixDebugCapture,
    explain_debug_line,
    parse_debug_line,
    redact_debug_text,
    remote_debug_endpoint,
    resolve_phnix_debug_port,
    translation_for,
)


class FakeSource:
    description = "Lokal: COM17 / MI_04"

    def __init__(self):
        self.chunks = queue.Queue()
        self.closed = 0
        self.created_thread = None
        self.read_thread = None
        self.close_thread = None

    def read(self, size):
        self.read_thread = threading.get_ident()
        try:
            return self.chunks.get(timeout=0.02)
        except queue.Empty:
            return b""

    def close(self):
        self.close_thread = threading.get_ident()
        self.closed += 1


class PhnixDebugTests(unittest.TestCase):
    @staticmethod
    def _wait_for(predicate, timeout=1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        raise AssertionError("Zeitüberschreitung beim Warten auf DebugCapture")

    def test_capture_opens_once_and_lives_until_last_consumer_leaves(self):
        opens = []

        def factory():
            source = FakeSource()
            source.created_thread = threading.get_ident()
            opens.append(source)
            return source

        capture = PhnixDebugCapture(factory)
        self.assertTrue(capture.add_consumer("window", lambda *_: None))
        self.assertTrue(capture.add_consumer("update", lambda *_: None))
        self.assertEqual(len(opens), 1)
        capture.remove_consumer("window")
        self.assertTrue(capture.active)
        capture.remove_consumer("update")
        self._wait_for(lambda: opens[0].closed == 1)
        self.assertFalse(capture.active)
        self.assertEqual(opens[0].created_thread, opens[0].read_thread)
        self.assertEqual(opens[0].created_thread, opens[0].close_thread)

    def test_update_end_does_not_close_open_monitor(self):
        source = FakeSource()
        capture = PhnixDebugCapture(lambda: source)
        capture.add_consumer("window", lambda *_: None)
        capture.add_consumer("update", lambda *_: None)
        capture.remove_consumer("update")
        self.assertTrue(capture.active)
        self.assertEqual(source.closed, 0)
        capture.remove_consumer("window")
        self._wait_for(lambda: source.closed == 1)

    def test_exact_mi04_resolution_and_no_heuristic_fallback(self):
        records = [
            {"instance_id": r"USB\VID_1E0E&PID_9001&MI_03\A", "port": "COM6"},
            {"instance_id": r"USB\VID_1E0E&PID_9001&MI_04\A", "port": "COM17"},
        ]
        self.assertEqual(resolve_phnix_debug_port(records), "COM17")
        self.assertIsNone(resolve_phnix_debug_port(records[:1]))
        records.append({"instance_id": records[1]["instance_id"] + "2", "port": "COM18"})
        self.assertIsNone(resolve_phnix_debug_port(records))

    def test_remote_debug_is_adb_port_plus_one(self):
        self.assertEqual(remote_debug_endpoint("192.0.2.8", 5038), ("192.0.2.8", 5039))

    def test_secret_and_phnix_topic_redaction(self):
        for key in ("device_secret", "deviceSecret"):
            safe = redact_debug_text(
                f'{{"{key}":"real-secret","ICCID":"8988212345678901234",'
                '"IMEI":"123456789012345"}} /a1ProductKey/867530900000001/user/update'
            )
            self.assertNotIn("real-secret", safe)
            self.assertNotIn("8988212345678901234", safe)
            self.assertNotIn("123456789012345", safe)
            self.assertNotIn("a1ProductKey", safe)
            self.assertNotIn("867530900000001", safe)
            self.assertIn("/<REDACTED>/<REDACTED>/user/update", safe)

    def test_parser_progress_and_invalid_values(self):
        event = parse_debug_line("tal_len:46C0E,and:43B78,len;0,idx:183")
        self.assertEqual((event.total, event.current), (289806, 277368))
        self.assertAlmostEqual(event.progress, 95.7, places=1)
        self.assertIsNone(parse_debug_line("tal_len:10,and:11"))
        self.assertIsNone(parse_debug_line("tal_len:0,and:0"))

    def test_cloud_and_manufacturer_messages_are_never_terminal_success(self):
        transfer = parse_debug_line('sendBuf: {"cmd":"CMD_OTA","code":"0043","progress":"100"}')
        complete = parse_debug_line("升级包传输完成")
        manufacturer = parse_debug_line("主板升级成功<5>")
        mqtt = parse_debug_line("IOT_MQTT_CheckStateNormal = 1")
        self.assertEqual(transfer.progress, 100)
        self.assertFalse(transfer.terminal_success)
        self.assertFalse(complete.terminal_success)
        self.assertTrue(manufacturer.manufacturer_success)
        self.assertFalse(manufacturer.terminal_success)
        self.assertEqual(mqtt.kind, "mqtt-normal")

    def test_translations_are_written_after_original(self):
        line = "[PHNIX] 升级包传输完成"
        self.assertIn("Firmwarepaket", translation_for(line))
        explained = explain_debug_line(line)
        self.assertTrue(explained.startswith(line + "\n"))
        for sim_error in ("获取sim卡iccid失败", "获取sim卡imsi失败"):
            self.assertIsNotNone(translation_for(sim_error))
            self.assertIsNone(parse_debug_line(sim_error))

    def test_simulator_excerpt_remains_supplementary_diagnostics(self):
        lines = (Path(__file__).parent / "fixtures" / "phnix_debug_excerpt.log").read_text(
            encoding="utf-8"
        ).splitlines()
        events = [event for line in lines if (event := parse_debug_line(line))]
        progress = [event.progress for event in events if event.kind == "transfer-progress"]
        expected = [95.7089, 97.4454, 99.1884, 99.9979]
        self.assertEqual(len(progress), len(expected))
        for actual, wanted in zip(progress, expected):
            self.assertAlmostEqual(actual, wanted, places=1)
        self.assertTrue(all(not event.terminal_success for event in events))


if __name__ == "__main__":
    unittest.main()
