import queue
import threading
import time
import unittest
from unittest.mock import patch
from pathlib import Path

from updater.common.phnix_debug import (
    PhnixDebugCapture,
    SerialCompletionSequence,
    TcpDebugSource,
    completion_events_for_line,
    explain_debug_line,
    parse_debug_line,
    redact_debug_text,
    remote_debug_endpoint,
    resolve_phnix_debug_port,
    translation_for,
    translations_for,
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
        self._wait_for(lambda: capture.active)
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
        self._wait_for(lambda: capture.active)
        capture.remove_consumer("update")
        self.assertTrue(capture.active)
        self.assertEqual(source.closed, 0)
        capture.remove_consumer("window")
        self._wait_for(lambda: source.closed == 1)

    def test_immediate_last_consumer_reconnect_keeps_single_reader(self):
        class BlockingSource(FakeSource):
            def __init__(self):
                super().__init__()
                self.read_started = threading.Event()
                self.release_read = threading.Event()
                self.first_read = True

            def read(self, size):
                self.read_thread = threading.get_ident()
                if self.first_read:
                    self.first_read = False
                    self.read_started.set()
                    self.release_read.wait(1.0)
                    return b""
                return super().read(size)

        opens = []

        def factory():
            source = BlockingSource()
            source.created_thread = threading.get_ident()
            opens.append(source)
            return source

        capture = PhnixDebugCapture(factory)
        self.assertTrue(capture.add_consumer("window", lambda *_: None))
        self.assertTrue(opens[0].read_started.wait(1.0))
        capture.remove_consumer("window")
        self.assertTrue(capture.add_consumer("window", lambda *_: None))
        opens[0].release_read.set()
        time.sleep(0.05)
        self.assertTrue(capture.active)
        self.assertEqual(len(opens), 1)
        self.assertEqual(opens[0].closed, 0)
        capture.remove_consumer("window")
        self._wait_for(lambda: opens[0].closed == 1)

    def test_status_consumer_can_suppress_initial_disconnected_notification(self):
        statuses = []
        capture = PhnixDebugCapture(lambda: FakeSource())
        capture.add_status_consumer("log", lambda status, error: statuses.append(status), notify_initial=False)
        self.assertEqual(statuses, [])

    def test_add_consumer_returns_without_waiting_for_slow_open(self):
        release = threading.Event()

        def factory():
            release.wait(1.0)
            return FakeSource()

        capture = PhnixDebugCapture(factory)
        started = time.monotonic()
        self.assertTrue(capture.add_consumer("window", lambda *_: None))
        self.assertLess(time.monotonic() - started, 0.1)
        release.set()
        capture.remove_consumer("window")

    def test_async_source_open_failure_is_reported_asynchronously(self):
        release = threading.Event()
        statuses = []

        def factory():
            release.wait(1.0)
            raise OSError("open failed")

        capture = PhnixDebugCapture(factory)
        capture.add_status_consumer("ui", lambda status, error: statuses.append(status))
        started = time.monotonic()
        self.assertTrue(capture.add_consumer("update", lambda *_: None))
        self.assertLess(time.monotonic() - started, 0.1)
        release.set()
        self._wait_for(lambda: capture.status == "Verbindung fehlgeschlagen")
        self.assertIn("Verbindung fehlgeschlagen", statuses)

    def test_empty_reads_have_reader_backoff(self):
        class EmptySource(FakeSource):
            def __init__(self):
                super().__init__()
                self.reads = 0

            def read(self, size):
                self.reads += 1
                return b""

        source = EmptySource()
        capture = PhnixDebugCapture(lambda: source)
        capture.add_consumer("window", lambda *_: None)
        time.sleep(0.08)
        capture.remove_consumer("window")
        self.assertLess(source.reads, 10)

    def test_unterminated_pending_data_is_bounded(self):
        received = []

        class Source(FakeSource):
            def read(self, size):
                if not received:
                    received.append(True)
                    return b"x" * 1_100_000
                raise ConnectionError("done")

        capture = PhnixDebugCapture(lambda: Source())
        capture.add_consumer("window", lambda line, event: None)
        self._wait_for(lambda: capture.status == "Verbindung beendet")
        self.assertFalse(capture.active)

    def test_exact_mi04_resolution_and_no_heuristic_fallback(self):
        records = [
            {"instance_id": r"USB\VID_1E0E&PID_9001&MI_03\A", "port": "COM6"},
            {"instance_id": r"USB\VID_1E0E&PID_9001&MI_04\A", "port": "COM17"},
        ]
        self.assertEqual(resolve_phnix_debug_port(records), "COM17")
        self.assertIsNone(resolve_phnix_debug_port(records[:1]))
        records.append({"instance_id": records[1]["instance_id"] + "2", "port": "COM18"})
        self.assertIsNone(resolve_phnix_debug_port(records))

    def test_windows_resolution_ignores_stale_mi04_instances(self):
        records = [
            {"instance_id": rf"USB\VID_1E0E&PID_9001&MI_04\{port}", "port": port}
            for port in ("COM6", "COM11", "COM16")
        ]
        self.assertEqual(
            resolve_phnix_debug_port(records, ["COM3", "COM14", "COM16", "COM17"]),
            "COM16",
        )
        self.assertIsNone(resolve_phnix_debug_port(records, ["COM3", "COM14"]))

    @patch("updater.common.phnix_debug._windows_pnp_records", return_value=[])
    def test_stale_registry_com16_is_absent_without_present_pnp_device(self, _records):
        self.assertIsNone(resolve_phnix_debug_port())

    @patch(
        "updater.common.phnix_debug._windows_pnp_records",
        return_value=[
            {"instance_id": r"USB\VID_1E0E&PID_9001&MI_04\PRESENT", "port": "COM16"}
        ],
    )
    def test_present_pnp_mi04_com16_is_resolved(self, _records):
        self.assertEqual(resolve_phnix_debug_port(), "COM16")

    def test_windows_resolution_never_uses_other_interfaces(self):
        records = [
            {"instance_id": rf"USB\VID_1E0E&PID_9001&MI_0{interface}\A", "port": f"COM{interface}"}
            for interface in (0, 1, 2)
        ]
        self.assertIsNone(resolve_phnix_debug_port(records, ["COM0", "COM1", "COM2"]))

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

    def test_phnix_identifier_variants_and_error_payload_are_redacted(self):
        safe = redact_debug_text(
            "ccid = 8988212345678901234 deviceName:359712345678901 "
            "deviceID_03=board-identity "
            "payload: error:0,18,8988212345678901234,359712345678901,/,823002250012,0/0"
        )
        self.assertNotIn("8988212345678901234", safe)
        self.assertNotIn("359712345678901", safe)
        self.assertNotIn("board-identity", safe)
        self.assertIn("payload: error:0,18,<REDACTED>,<REDACTED>,/,823002250012,0/0", safe)

    def test_serial_completion_requires_ordered_current_generation_sequence(self):
        events = [
            parse_debug_line("升级包传输完成"),
            parse_debug_line("主板升级成功<5>"),
            parse_debug_line("CMD_OTA code 0053 progress 100"),
            parse_debug_line("主板升级结束"),
        ]
        sequence = SerialCompletionSequence(7)
        for event in events[:-1]:
            self.assertFalse(sequence.observe(event, 7))
        self.assertTrue(sequence.observe(events[-1], 7))

        old = SerialCompletionSequence(6)
        self.assertFalse(any(old.observe(event, 7) for event in events))
        incomplete = SerialCompletionSequence(8)
        self.assertFalse(incomplete.observe(events[1], 8))
        self.assertFalse(incomplete.observe(events[2], 8))
        self.assertFalse(incomplete.observe(events[3], 8))

    def test_glued_completion_messages_keep_manufacturer_and_0053_events(self):
        events = completion_events_for_line(
            "主板升级成功<5> ... CMD_OTA code 0053 progress 100"
        )
        self.assertEqual(
            [(event.kind, event.code, event.progress) for event in events],
            [
                ("manufacturer-success", None, None),
                ("cloud-progress", "0053", 100.0),
            ],
        )

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

    def test_download_is_separate_from_mainboard_and_cloud_progress(self):
        download = parse_debug_line("download 100%")
        cloud = parse_debug_line('CMD_OTA code=0043 progress=100')
        transfer = parse_debug_line("tal_len:46C0E,and:B52,len;0")
        self.assertEqual(download.kind, "lte-download-progress")
        self.assertEqual(cloud.kind, "cloud-progress")
        self.assertEqual(transfer.kind, "transfer-progress")
        self.assertAlmostEqual(transfer.progress, 1.0, places=1)
        self.assertTrue(all(not event.terminal_success for event in (download, cloud, transfer)))

    def test_multiple_translations_and_unknown_chinese_marker(self):
        line = "上报服务器此轮升级失败oat step:12publish success, packet-id=433"
        explanations = translations_for(line)
        self.assertEqual(len(explanations), 2)
        rendered = explain_debug_line(line)
        self.assertIn("OTA-Runde", rendered)
        self.assertIn("MQTT Publish erfolgreich", rendered)
        self.assertIn("Noch keine deutsche Erläuterung", explain_debug_line("尚未识别的文本"))
        self.assertNotIn("Noch keine deutsche Erläuterung", explain_debug_line("ASCII only"))

    def test_new_translations_and_dynamic_numbers(self):
        expected = {
            "主板收到服务器新固件信息，回复允许升级": "neue Firmwareinformationen",
            "主板允许升级": "Firmwareupdate",
            "board固件MD5校验正确！": "MD5-Prüfung",
            "获取IMEI": "IMEI",
            "重新采集WF": "WF-Information",
            "等待获取主板productKey": "ProductKey",
            "重新采集pk": "ProductKey",
            "等待获取主板2deviceSecret": "DeviceSecret",
        }
        for original, german in expected.items():
            self.assertIn(german, explain_debug_line(original))
        self.assertIn("12345", explain_debug_line("下载主板升级文件长度:12345"))
        self.assertIn("0x20", explain_debug_line("传输主板升级文件偏移:0x20"))

    def test_tcp_timeout_stays_open_but_eof_disconnects(self):
        class Socket:
            def __init__(self):
                self.values = [__import__("socket").timeout(), b""]
                self.closed = False

            def settimeout(self, _value):
                pass

            def recv(self, _size):
                value = self.values.pop(0)
                if isinstance(value, Exception):
                    raise value
                return value

            def close(self):
                self.closed = True

        sock = Socket()
        with patch("updater.common.phnix_debug.socket.create_connection", return_value=sock):
            source = TcpDebugSource("192.0.2.8", 5039)
        self.assertEqual(source.read(10), b"")
        with self.assertRaisesRegex(ConnectionError, "TCP-Verbindung beendet"):
            source.read(10)

    def test_capture_reports_eof_once_without_busy_loop(self):
        class EofSource(FakeSource):
            def __init__(self):
                super().__init__()
                self.reads = 0

            def read(self, size):
                self.reads += 1
                raise ConnectionError("TCP-Verbindung beendet")

        source = EofSource()
        capture = PhnixDebugCapture(lambda: source, "remote:192.0.2.8:5039")
        capture.add_consumer("window", lambda *_: None)
        self._wait_for(lambda: source.closed == 1)
        self.assertEqual(source.reads, 1)
        self.assertFalse(capture.active)
        self.assertEqual(capture.status, "Verbindung beendet")

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
