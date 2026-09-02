import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from updater.dtu_ota.diagnostics import create_bundle, redact_text


class FakeAdb:
    def __init__(self):
        self.files = {
            "/data/foxair_ota_runner/last_run_id": b"run-42\n",
            "/data/foxair_ota_runner/runs/run-42/status.json": b'{"state":"completed","deviceCode":"860147058259753"}\n',
            "/data/foxair_ota_runner/runs/run-42/runner.log": b"service restart verified\n",
            "/data/foxair_ota_runner/runs/run-42/package.json": b'{"firmware_file":"firmware.bin"}\n',
            "/data/foxair_ota_runner/runs/run-42/state/OTA_INFO": b"MUST-NOT-BE-INCLUDED",
            "/data/foxair_ota_runner/runs/run-42/payload/firmware.bin": b"FIRMWARE-MUST-NOT-BE-INCLUDED",
        }

    def shell(self, command, check=True):
        if command.startswith("cat /data/foxair_ota_runner/active.lock/run_id"):
            return ""
        if command.startswith("cat /data/foxair_ota_runner/last_run_id"):
            return "run-42"
        if command.startswith("ls -1 '/data/foxair_ota_runner/runs'"):
            return "run-42"
        if command.startswith("if [ -f '"):
            remote = command.split("'", 2)[1]
            return "PRESENT" if remote in self.files else "ABSENT"
        if "SERVICE_PID=$(pidof phnixIot4G" in command:
            return "boot_id=test-boot\nservice_pids=123\nservice_tracer_pid=0"
        return ""

    def read_file(self, remote):
        return self.files[remote]


class SameDayFakeAdb(FakeAdb):
    RUN1 = "20260902-140000-0001"
    RUN2 = "20260902-145000-0002"
    OLD = "20260901-230000-0003"

    def __init__(self):
        super().__init__()
        self.files = {
            "/data/foxair_ota_runner/last_run_id": (self.RUN2 + "\n").encode(),
            f"/data/foxair_ota_runner/runs/{self.RUN1}/status.json": b'{"state":"failed"}\n',
            f"/data/foxair_ota_runner/runs/{self.RUN1}/runner.log": b"first attempt\n",
            f"/data/foxair_ota_runner/runs/{self.RUN2}/status.json": b'{"state":"completed"}\n',
            f"/data/foxair_ota_runner/runs/{self.RUN2}/runner.log": b"second attempt\n",
            f"/data/foxair_ota_runner/runs/{self.OLD}/status.json": b'{"state":"old"}\n',
        }

    def shell(self, command, check=True):
        if command.startswith("cat /data/foxair_ota_runner/active.lock/run_id"):
            return ""
        if command.startswith("cat /data/foxair_ota_runner/last_run_id"):
            return self.RUN2
        if command.startswith("ls -1 '/data/foxair_ota_runner/runs'"):
            return "\n".join((self.OLD, self.RUN2, self.RUN1))
        if command.startswith("if [ -f '"):
            remote = command.split("'", 2)[1]
            return "PRESENT" if remote in self.files else "ABSENT"
        if "SERVICE_PID=$(pidof phnixIot4G" in command:
            return "boot_id=test-boot\nservice_pids=123\nservice_tracer_pid=0"
        return ""


class DiagnosticBundleTests(unittest.TestCase):
    def test_redaction_masks_known_cloud_and_device_identifiers(self):
        text = 'device_secret=abc123 productKey:key123 IMEI:860147058259753 ccid=89330112407972705790'
        value = redact_text(text)
        self.assertNotIn("abc123", value)
        self.assertNotIn("key123", value)
        self.assertNotIn("860147058259753", value)
        self.assertNotIn("89330112407972705790", value)

    def test_bundle_uses_text_whitelist_and_excludes_binary_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            host_log = root / "gui.log"
            host_log.write_text('deviceCode:860147058259753\nGUI line\n', encoding="utf-8")
            output = root / "diag.zip"
            result = create_bundle(FakeAdb(), output, host_log=host_log, app_version="0.4.0")
            self.assertTrue(result["ok"])
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn("dtu-run/status.json", names)
                self.assertIn("dtu-run/runner.log", names)
                self.assertIn("host/foxair-updater.log", names)
                self.assertIn("diagnostic_manifest.json", names)
                self.assertNotIn("dtu-run/state/OTA_INFO", names)
                self.assertNotIn("dtu-run/payload/firmware.bin", names)
                combined = "\n".join(
                    archive.read(name).decode("utf-8", errors="replace")
                    for name in names
                    if name.endswith((".json", ".log", ".txt"))
                )
                self.assertNotIn("860147058259753", combined)
                manifest = json.loads(archive.read("diagnostic_manifest.json"))
                self.assertFalse(manifest["privacy"]["firmware_included"])
                self.assertFalse(manifest["privacy"]["ota_info_binary_included"])
                self.assertFalse(manifest["privacy"]["statistics_binary_included"])

    def test_bundle_collects_all_runner_attempts_and_host_logs_from_same_day(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log_dir = root / "Logs"
            log_dir.mkdir()
            (log_dir / "FoxAir_Update_20260902-140001.log").write_text("host first\n", encoding="utf-8")
            (log_dir / "FoxAir_Update_20260902-145001_LTE.log").write_text("host second\n", encoding="utf-8")
            (log_dir / "FoxAir_Update_20260901-230001.log").write_text("old host\n", encoding="utf-8")
            output = root / "diag.zip"
            result = create_bundle(
                SameDayFakeAdb(), output, host_log_dir=log_dir, app_version="0.4.0"
            )
            self.assertEqual(result["run_ids"], [SameDayFakeAdb.RUN1, SameDayFakeAdb.RUN2])
            self.assertEqual(len(result["host_logs"]), 2)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn(f"dtu-runs/{SameDayFakeAdb.RUN1}/runner.log", names)
                self.assertIn(f"dtu-runs/{SameDayFakeAdb.RUN2}/runner.log", names)
                self.assertNotIn(f"dtu-runs/{SameDayFakeAdb.OLD}/status.json", names)
                self.assertIn("host/day/FoxAir_Update_20260902-140001.log", names)
                self.assertIn("host/day/FoxAir_Update_20260902-145001_LTE.log", names)
                self.assertNotIn("host/day/FoxAir_Update_20260901-230001.log", names)
                manifest = json.loads(archive.read("diagnostic_manifest.json"))
                self.assertEqual(manifest["schema"], "foxair-diagnostic-bundle-v2")
                self.assertEqual(manifest["run_day"], "20260902")
                self.assertEqual(manifest["run_ids"], [SameDayFakeAdb.RUN1, SameDayFakeAdb.RUN2])


if __name__ == "__main__":
    unittest.main()
