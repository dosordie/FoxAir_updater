import queue
from pathlib import Path

import pytest

from updater.common.phnix_debug import (
    PhnixDebugCapture,
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

    def read(self, size):
        try:
            return self.chunks.get(timeout=0.02)
        except queue.Empty:
            return b""

    def close(self):
        self.closed += 1


def test_capture_opens_once_and_lives_until_last_consumer_leaves():
    opens = []

    def factory():
        source = FakeSource()
        opens.append(source)
        return source

    capture = PhnixDebugCapture(factory)
    received = []
    assert capture.add_consumer("window", lambda line, event: received.append(line))
    assert capture.add_consumer("update", lambda line, event: received.append(line))
    assert len(opens) == 1
    capture.remove_consumer("window")
    assert capture.active
    capture.remove_consumer("update")
    assert not capture.active
    assert opens[0].closed == 1


def test_update_end_does_not_close_open_monitor():
    source = FakeSource()
    capture = PhnixDebugCapture(lambda: source)
    capture.add_consumer("window", lambda *_: None)
    capture.add_consumer("update", lambda *_: None)
    capture.remove_consumer("update")
    assert capture.active and source.closed == 0
    capture.remove_consumer("window")
    assert source.closed == 1


def test_exact_mi04_resolution_and_no_heuristic_fallback():
    records = [
        {"instance_id": r"USB\VID_1E0E&PID_9001&MI_03\A", "port": "COM6"},
        {"instance_id": r"USB\VID_1E0E&PID_9001&MI_04\A", "port": "COM17"},
    ]
    assert resolve_phnix_debug_port(records) == "COM17"
    assert resolve_phnix_debug_port(records[:1]) is None
    assert resolve_phnix_debug_port(records + [{"instance_id": records[1]["instance_id"] + "2", "port": "COM18"}]) is None


def test_remote_debug_is_adb_port_plus_one():
    assert remote_debug_endpoint("192.0.2.8", 5038) == ("192.0.2.8", 5039)


@pytest.mark.parametrize("key", ["device_secret", "deviceSecret"])
def test_secret_redaction(key):
    safe = redact_debug_text(f'{{"{key}":"real-secret","ICCID":"8988212345678901234","IMEI":"123456789012345"}}')
    assert "real-secret" not in safe
    assert "8988212345678901234" not in safe
    assert "123456789012345" not in safe
    assert "<REDACTED>" in safe


def test_parser_progress_and_invalid_values():
    event = parse_debug_line("tal_len:46C0E,and:43B78,len;0,idx:183")
    assert (event.total, event.current) == (289806, 277368)
    assert event.progress == pytest.approx(95.7089, rel=1e-4)
    assert parse_debug_line("tal_len:10,and:11") is None
    assert parse_debug_line("tal_len:0,and:0") is None


def test_cloud_and_manufacturer_messages_are_never_terminal_success():
    transfer = parse_debug_line('sendBuf: {"cmd":"CMD_OTA","code":"0043","progress":"100"}')
    complete = parse_debug_line("升级包传输完成")
    manufacturer = parse_debug_line("主板升级成功<5>")
    assert transfer.progress == 100 and not transfer.terminal_success
    assert not complete.terminal_success
    assert manufacturer.manufacturer_success and not manufacturer.terminal_success


def test_confirmed_translations_and_sim_errors_are_diagnostics_only():
    assert "Firmwarepaket" in translation_for("[PHNIX] 升级包传输完成")
    for line in ("获取sim卡iccid失败", "获取sim卡imsi失败"):
        assert translation_for(line)
        assert parse_debug_line(line) is None


def test_simulator_excerpt_remains_supplementary_diagnostics():
    lines = (Path(__file__).parent / "fixtures" / "phnix_debug_excerpt.log").read_text(
        encoding="utf-8"
    ).splitlines()
    events = [event for line in lines if (event := parse_debug_line(line))]
    assert [event.progress for event in events if event.kind == "transfer-progress"] == pytest.approx(
        [95.7089, 97.4454, 99.1884, 99.9979], rel=1e-4
    )
    assert all(not event.terminal_success for event in events)
