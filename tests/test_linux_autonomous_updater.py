import tempfile
import unittest
from pathlib import Path
from unittest import mock

from updater.linux import autonomous_update as linux


class FakeLog:
    def __init__(self, root: Path):
        self.path = root / "host.log"
        self.path.write_text("host\n", encoding="utf-8")
        self.lines = []

    def write(self, text, *, error=False):
        self.lines.append((text, error))


class FakeAdb:
    def __init__(self):
        self.commands = []

    def shell(self, command, check=True):
        self.commands.append(command)
        return ""


class FakeClient:
    def __init__(self):
        self.adb = FakeAdb()
        self.calls = []
        self.active = None
        self.prepared = {
            "run_id": "20260928-080000-0001",
            "state": "prepared",
            "phase": "dry-run-complete",
            "terminal": False,
            "transfer_started": False,
            "original_service_authoritative": False,
        }

    def prepare(self, **kwargs):
        self.calls.append(("prepare", kwargs))
        return dict(self.prepared)

    def start(self, run_id):
        self.calls.append(("start", run_id))
        return {
            "run_id": run_id,
            "state": "running",
            "phase": "local-preparation",
            "terminal": False,
        }

    def acknowledge(self, run_id):
        self.calls.append(("ack", run_id))
        return {"run_id": run_id, "terminal": True}

    def cleanup(self, run_id):
        self.calls.append(("cleanup", run_id))

    def active_run_id(self):
        return self.active


class LinuxAutonomousUpdaterTests(unittest.TestCase):
    def test_success_archives_before_ack_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            client = FakeClient()
            log = FakeLog(root)
            archive = root / "FoxAir_DTU_Logs_20260928-080000-0001.zip"
            archive.write_bytes(b"zip")
            status = {
                "run_id": "20260928-080000-0001",
                "terminal": True,
                "result_type": "success",
            }
            events = []

            def diagnostic(*args, **kwargs):
                events.append("archive")
                return archive

            original_ack = client.acknowledge
            original_cleanup = client.cleanup
            client.acknowledge = lambda run_id: (events.append("ack"), original_ack(run_id))[1]
            client.cleanup = lambda run_id: (events.append("cleanup"), original_cleanup(run_id))[1]

            with mock.patch.object(linux, "create_diagnostic_bundle", side_effect=diagnostic):
                rc = linux.finalize_status(
                    client,
                    client.adb,
                    status,
                    logs_dir=root,
                    run_log=log,
                    version="test",
                )

            self.assertEqual(rc, 0)
            self.assertEqual(events, ["archive", "ack", "cleanup"])

    def test_failure_is_archived_but_never_acknowledged_or_cleaned(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            client = FakeClient()
            log = FakeLog(root)
            archive = root / "FoxAir_DTU_Logs_20260928-080000-0001.zip"
            archive.write_bytes(b"zip")
            status = {
                "run_id": "20260928-080000-0001",
                "terminal": True,
                "result_type": "failed",
            }
            with mock.patch.object(linux, "create_diagnostic_bundle", return_value=archive):
                rc = linux.finalize_status(
                    client,
                    client.adb,
                    status,
                    logs_dir=root,
                    run_log=log,
                    version="test",
                )

            self.assertEqual(rc, 2)
            self.assertFalse(any(call[0] in {"ack", "cleanup"} for call in client.calls))

    def test_archive_failure_blocks_ack_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            client = FakeClient()
            log = FakeLog(root)
            status = {
                "run_id": "20260928-080000-0001",
                "terminal": True,
                "result_type": "success",
            }
            with mock.patch.object(
                linux, "create_diagnostic_bundle", side_effect=linux.CliError("broken")
            ):
                rc = linux.finalize_status(
                    client,
                    client.adb,
                    status,
                    logs_dir=root,
                    run_log=log,
                    version="test",
                )

            self.assertEqual(rc, 2)
            self.assertFalse(any(call[0] in {"ack", "cleanup"} for call in client.calls))

    def test_update_always_uses_full_runner_mode_restart_and_normal_mqtt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            client = FakeClient()
            log = FakeLog(root)
            manifest = root / "FW3.5.json"
            manifest.write_text("{}", encoding="utf-8")
            with mock.patch.object(linux, "monitor_run", return_value=0) as monitor:
                rc = linux.run_update(
                    client,
                    client.adb,
                    manifest,
                    logs_dir=root,
                    run_log=log,
                    version="test",
                )

            self.assertEqual(rc, 0)
            prepare = client.calls[0]
            self.assertEqual(prepare[0], "prepare")
            self.assertEqual(prepare[1]["mode"], "full")
            self.assertTrue(prepare[1]["restart_service_before_update"])
            self.assertFalse(prepare[1]["isolate_mqtt"])
            self.assertEqual(client.calls[1], ("start", "20260928-080000-0001"))
            monitor.assert_called_once()

    def test_check_removes_only_a_proven_prepared_non_active_run(self):
        client = FakeClient()
        linux.discard_prepared_run(client, dict(client.prepared))
        self.assertEqual(len(client.adb.commands), 1)
        self.assertIn("20260928-080000-0001", client.adb.commands[0])

        unsafe = dict(client.prepared, transfer_started=True)
        with self.assertRaises(linux.CliError):
            linux.discard_prepared_run(client, unsafe)

        client.active = "another-run"
        with self.assertRaises(linux.CliError):
            linux.discard_prepared_run(client, dict(client.prepared))


if __name__ == "__main__":
    unittest.main()
