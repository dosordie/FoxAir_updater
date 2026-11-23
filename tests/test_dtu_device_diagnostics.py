"""Regression tests for passive DTU identity/time/version diagnostics."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from updater.common.dtu_device_diagnostics import (
    OTA_INFO_LENGTH, classify_clock, parse_ota_info_version,
    read_dtu_identity, read_time_network,
)
from updater.dtu_ota.build_profiles import V10, V12
from updater.dtu_ota.diagnostics import ota_info_summary


def ota_info(version: bytes = b"V1.0") -> bytes:
    data = bytearray(OTA_INFO_LENGTH)
    data[28:28 + len(version)] = version
    return bytes(data)


class FakeAdb:
    def __init__(self, version=b"V1.0", sha=V10.service_sha256):
        self.data = ota_info(version) if version is not None else None
        self.sha = sha
        self.commands = []

    def read_file(self, path):
        self.commands.append(("read", path))
        if self.data is None:
            raise RuntimeError("no OTA_INFO")
        return self.data

    def shell(self, command, check=True):
        self.commands.append(("shell", command))
        if "sha256sum" in command:
            return self.sha
        if "date -u" in command:
            return "1980-01-07T02:42:07Z"
        if "/proc/uptime" in command:
            return "96126.34 12345.00"
        if "time_daemon" in command:
            return "598"
        if "/dev/rtc*" in command:
            return "/dev/rtc0"
        if "/sys/class/rtc" in command:
            return "1970-01-01 00:00:03"
        if "/proc/net/route" in command:
            return "rmnet_data0"
        if "netstat -nt" in command:
            return "tcp 0 0 10.0.0.1:34320 1.2.3.4:1883 ESTABLISHED"
        raise AssertionError("unexpected command " + command)


class DtuDiagnosticsTests(unittest.TestCase):
    def test_parses_persisted_ascii_version_only_with_valid_layout(self):
        self.assertEqual(parse_ota_info_version(ota_info()), "V1.0")
        self.assertEqual(parse_ota_info_version(ota_info(b"V1.2")), "V1.2")
        self.assertIsNone(parse_ota_info_version(b"V1.0"))
        self.assertIsNone(parse_ota_info_version(ota_info(b"bad!")))
        self.assertIsNone(parse_ota_info_version(ota_info(b"V1.0evil")))
        summary = ota_info_summary(ota_info(b"V1.2"))
        self.assertEqual(summary["stored_dtu_version"], "V1.2")

    def test_known_builds_derive_version_from_hash_not_stored_text(self):
        result = read_dtu_identity(FakeAdb())
        self.assertEqual(result["service_version"], "V1.0")
        self.assertEqual(result["stored_version"], "V1.0")
        self.assertTrue(result["supported"])
        self.assertEqual(result["build_status"], "supported")
        result = read_dtu_identity(FakeAdb(version=b"V1.0", sha=V12.service_sha256))
        self.assertEqual(result["service_version"], "V1.2")
        self.assertFalse(result["version_match"])

    def test_unknown_or_unreadable_build_is_never_supported(self):
        result = read_dtu_identity(FakeAdb(sha="a" * 64))
        self.assertEqual(result["stored_version"], "V1.0")
        self.assertEqual(result["build_status"], "unknown")
        self.assertIsNone(result["service_version"])
        self.assertFalse(result["supported"])
        self.assertIsNone(result["version_match"])
        result = read_dtu_identity(FakeAdb(version=None, sha=""))
        self.assertEqual(result["build_status"], "unreadable")
        self.assertEqual(result["stored_status"], "not_available")
        self.assertFalse(result["supported"])

    def test_clock_gps_epoch_with_uptime(self):
        host = datetime(2026, 11, 23, tzinfo=timezone.utc)
        result = classify_clock("1980-01-07T02:42:07Z", 96126.34, host_now=host)
        self.assertEqual(result["state"], "unsynchronized")
        self.assertTrue(result["possible_gps_epoch"])
        self.assertIn("1980-01-06", result["approximate_boot_utc"])
        same = classify_clock("2026-11-23T00:00:10Z", 100, host_now=host)
        self.assertEqual(same["state"], "plausible")
        self.assertEqual(classify_clock("bad", None, host_now=host)["state"], "unavailable")

    def test_passive_network_checks_do_not_send_at_or_mutate_service(self):
        adb = FakeAdb()
        values = read_time_network(adb)
        self.assertTrue(values["time_daemon_running"])
        self.assertTrue(values["mqtt_tcp_established"])
        self.assertTrue(values["mobile_route_present"])
        self.assertIsNone(values["modem_clock"])
        self.assertEqual(values["cloud_account_binding"], "unknown")
        cmds = [command for kind, command in adb.commands if kind == "shell"]
        for command in cmds:
            self.assertNotIn("AT+", command)
            self.assertNotIn("kill ", command)
            self.assertNotIn("date -s", command)
            self.assertNotIn("gdb ", command)


if __name__ == "__main__":
    unittest.main()
