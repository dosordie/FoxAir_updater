"""No-write, no-GDB live-state probe tests for pinned V1.0."""
from __future__ import annotations

import re
import unittest

from devtools.phnix_ota_v10.probe_runtime import probe
from updater.dtu_ota.build_profiles import V10, V12


class ProbeAdb:
    def __init__(self, sha=V10.service_sha256, pids="100", tracer="0"):
        self.sha = sha
        self.pids = pids
        self.tracer = tracer
        self.calls = []

    def shell(self, command, check=True):
        self.calls.append(command)
        if "sha256sum '/data/phnixIot4G'" in command:
            return self.sha
        if command == "pidof phnixIot4G":
            return self.pids
        if "TracerPid:" in command:
            return self.tracer
        if "dd if=/proc/" in command and "| od -An -v -tx1" in command:
            addr = int(re.search(r"skip=(\d+)", command).group(1))
            observed = {
                V10.dtu_run_step: 11,
                V10.dtu_sta: 4,
                V10.board_ota_step: 12,
                V10.uart_send_flag: 0,
            }
            self.assert_safe_read(command)
            return f"{observed[addr]:02x}"
        raise AssertionError("Unexpected operation: " + command)

    @staticmethod
    def assert_safe_read(command):
        assert "count=1" in command
        assert " of=" not in command
        assert "/dev/tty" not in command


class V10ReadOnlyProbeTests(unittest.TestCase):
    def test_v10_reads_exactly_four_single_bytes(self):
        adb = ProbeAdb()
        value = probe(adb)
        self.assertTrue(value["hypothesis_idle_v12_semantics"])
        self.assertFalse(value["ota_authorized"])
        reads = [x for x in adb.calls if "dd if=/proc/" in x]
        self.assertEqual(len(reads), 4)
        self.assertTrue(all("count=1" in x for x in reads))
        self.assertFalse(any("gdb" in x or "push" in x for x in adb.calls))

    def test_other_build_is_rejected_before_any_ram_read(self):
        adb = ProbeAdb(sha=V12.service_sha256)
        with self.assertRaises(ValueError):
            probe(adb)
        self.assertEqual(len(adb.calls), 1)

    def test_multiple_pids_or_existing_tracer_are_rejected(self):
        for pids, tracer in (("100 200", "0"), ("100", "123")):
            with self.subTest(pids=pids, tracer=tracer):
                adb = ProbeAdb(pids=pids, tracer=tracer)
                with self.assertRaises(ValueError):
                    probe(adb)
                self.assertFalse(any("dd if=/proc/" in x for x in adb.calls))


if __name__ == "__main__":
    unittest.main()
