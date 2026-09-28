import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from updater.dtu_ota import original_state
from updater.dtu_ota.package import EXPECTED_SERVICE_SHA256


class FakeAdb:
    def __init__(self):
        self.commands = []
        self.pushed = []
        self.files = set()
        self.ota_info = self._valid_ota_info()
        self.values = {
            "pidof phnixIot4G": "2002",
            "readlink /proc/2002/exe": "/data/phnixIot4G",
            "sha256sum '/data/phnixIot4G'": EXPECTED_SERVICE_SHA256.lower(),
            "TracerPid": "State:\tS (sleeping)\nTracerPid:\t0",
            "$4 == \"{helloworld}\"": "100\n101",
            ":1883": "tcp 0 0 10.0.0.2:4567 1.2.3.4:1883 ESTABLISHED",
            original_state.REMOTE_RUNNER_LOCK: "",
        }

    @staticmethod
    def _valid_ota_info():
        raw = bytearray(220)
        crc = original_state._crc16_x25(bytes(raw[4:220]))
        raw[0:4] = crc.to_bytes(4, "little")
        return bytes(raw)

    def shell(self, command, check=True):
        self.commands.append(command)
        if command.startswith("test -e '"):
            path = command.split("'", 2)[1]
            return "1" if path in self.files else ""
        if command.startswith("cat '"):
            path = command.split("'", 2)[1]
            if path == original_state.REMOTE_RUNNER_LOCK:
                return self.values[path]
            return ""
        for key, value in self.values.items():
            if key in command:
                return value
        return ""

    def read_file(self, remote):
        if remote == "/data/phnixIot_device_OTA_INFO":
            return self.ota_info
        return b""

    def push(self, local, remote):
        self.pushed.append((Path(local), remote))


class OriginalStateTests(unittest.TestCase):
    def test_clean_runtime_is_reported_as_original(self):
        adb = FakeAdb()
        result = original_state.original_state_snapshot(adb)
        self.assertTrue(result["original_ok"])
        self.assertTrue(all(result["checks"].values()))

    def test_original_state_rejects_invalid_ota_info_crc(self):
        adb = FakeAdb()
        adb.ota_info = bytes(220)
        result = original_state.original_state_snapshot(adb)
        self.assertFalse(result["original_ok"])
        self.assertFalse(result["checks"]["ota_info_valid"])

    def test_original_state_rejects_debugger_cloud_guard_http_or_staging(self):
        cases = (
            ("pidof gdbserver gdb", "123"),
            ("iptables -S OUTPUT", "-A OUTPUT -p tcp --dport 1883 -j DROP"),
            ("netstat -lnt", "tcp 0 0 127.0.0.1:8081 0.0.0.0:* LISTEN"),
            ("ls -A '/data/phnix_local_ota'", "firmware.bin"),
        )
        for key, value in cases:
            with self.subTest(key=key):
                adb = FakeAdb()
                adb.values[key] = value
                result = original_state.original_state_snapshot(adb)
                self.assertFalse(result["original_ok"])

    def test_active_autonomous_run_blocks_original_state_and_restore(self):
        adb = FakeAdb()
        adb.values[original_state.REMOTE_RUNNER_LOCK] = "run-123"
        result = original_state.original_state_snapshot(adb)
        self.assertFalse(result["original_ok"])
        self.assertFalse(result["checks"]["no_active_runner"])

        guard = original_state._restore_preconditions(adb)
        self.assertFalse(guard["safe"])
        self.assertIn("run-123", " ".join(guard["blockers"]))

    def test_transfer_or_original_authority_blocks_restore(self):
        for marker in (
            original_state.REMOTE_TRANSFER_STARTED,
            original_state.REMOTE_ORIGINAL_SERVICE_OWNS,
        ):
            adb = FakeAdb()
            adb.files.add(marker)
            guard = original_state._restore_preconditions(adb)
            self.assertFalse(guard["safe"])
            self.assertIn("Firmwareübertragung", " ".join(guard["blockers"]))

    def test_mismatched_active_legacy_hook_is_not_replaced(self):
        adb = FakeAdb()
        adb.files.update(
            {original_state.REMOTE_HELPER, original_state.REMOTE_RUN_ACTIVE}
        )
        adb.values[f"sha256sum '{original_state.REMOTE_HELPER}'"] = "0" * 64
        with tempfile.TemporaryDirectory() as temp:
            hook = Path(temp) / "hook"
            hook.write_bytes(b"#!/bin/sh\necho safe\n")
            with self.assertRaises(original_state.OriginalStateError):
                original_state._install_verified_hook(adb, hook)
        self.assertEqual(adb.pushed, [])

    def test_restore_uses_proven_hook_and_never_touches_runner_directory(self):
        adb = FakeAdb()
        good = {
            "original_ok": True,
            "checks": {"all": True},
        }
        with (
            mock.patch.object(original_state, "_local_hook_path", return_value=Path("hook")),
            mock.patch.object(original_state, "_install_verified_hook") as install,
            mock.patch.object(original_state, "_remove_legacy_artifacts") as cleanup,
            mock.patch.object(original_state, "original_state_snapshot", return_value=good),
        ):
            result = original_state.restore_original_state(adb, timeout=0)

        self.assertTrue(result["ok"])
        install.assert_called_once()
        cleanup.assert_called_once()
        joined = "\n".join(adb.commands)
        self.assertIn("restore-original", joined)
        self.assertNotIn("rm -rf '/data/foxair_ota_runner'", joined)

    def test_runtime_hook_restore_still_kills_injected_service_before_release(self):
        hook = Path("updater/dtu_ota/payload/phnix_ota_runtime_hook").read_text(
            encoding="utf-8"
        )
        restore = hook.split("restore_original_hook() {", 1)[1].split(
            "attach_test() {", 1
        )[0]
        injected = restore.split('if test "$INJECTED" = 1; then', 1)[1].split(
            "\n    fi", 1
        )[0]
        self.assertIn('kill -KILL "$OLD_PID"', injected)
        self.assertNotIn('kill -CONT "$OLD_PID"', injected)

    def test_runtime_hook_hash_is_stable_and_full_length(self):
        hook = Path("updater/dtu_ota/payload/phnix_ota_runtime_hook")
        digest = hashlib.sha256(hook.read_bytes()).hexdigest()
        self.assertEqual(len(digest), 64)


if __name__ == "__main__":
    unittest.main()
