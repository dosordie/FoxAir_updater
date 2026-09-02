import json
import unittest
from pathlib import Path

from updater.dtu_ota.client import DtuOtaClient, RunnerClientError


class StatusAdb:
    def __init__(self, status, active=""):
        self.status_value = status
        self.active = active

    def shell(self, command, check=True):
        if "active.lock/run_id" in command:
            return self.active
        if "last_run_id" in command:
            return self.status_value["run_id"]
        if "/status.json" in command:
            return json.dumps(self.status_value)
        return ""


class DtuOtaRestartCompatibilityTests(unittest.TestCase):
    def test_restart_tolerates_transient_multiple_service_pids(self):
        runner = Path("updater/dtu_ota/payload/dtu_ota_supervisor.sh").read_text(
            encoding="utf-8"
        )
        restart = runner.split("restart_service() {", 1)[1].split("start_http() {", 1)[0]
        self.assertNotIn('if test "$current_count" -gt 1; then return 2; fi', restart)
        self.assertIn('if test "$current_count" = 1; then', restart)
        self.assertIn('test "$is_old" = false && test "$old_alive" = false', restart)
        self.assertIn('test "$stable_count" -ge 10', restart)
        self.assertIn('TracerPid:', restart)

    def test_inactive_legacy_status_gets_safe_defaults(self):
        status = {
            "schema": "foxair-dtu-ota-run-v1",
            "run_id": "legacy-1",
            "state": "failed",
            "phase": "failed",
            "terminal": True,
            "updated_at": 1,
            "transfer_started": False,
            "original_service_authoritative": False,
            "abort_allowed": True,
            "recovery": "not-required",
        }
        client = DtuOtaClient(StatusAdb(status))
        value = client.status("legacy-1", reconcile=False)
        self.assertTrue(value["legacy_status"])
        self.assertFalse(value["service_restart_requested"])
        self.assertFalse(value["service_restart_verified"])
        self.assertFalse(value["mqtt_isolation_requested"])
        self.assertFalse(value["mqtt_isolated"])
        self.assertEqual(value["boot_id"], "")

    def test_active_legacy_status_still_fails_closed(self):
        status = {
            "schema": "foxair-dtu-ota-run-v1",
            "run_id": "legacy-active",
            "state": "running",
            "phase": "c5a8",
            "terminal": False,
            "updated_at": 1,
            "transfer_started": True,
            "original_service_authoritative": True,
            "abort_allowed": False,
            "recovery": "not-required",
        }
        client = DtuOtaClient(StatusAdb(status, active="legacy-active"))
        with self.assertRaisesRegex(RunnerClientError, "invalid status contract"):
            client.status("legacy-active", reconcile=False)


if __name__ == "__main__":
    unittest.main()
