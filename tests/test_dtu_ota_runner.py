import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.dtu_ota_runner.client import DtuOtaClient, RunnerClientError
from tools.dtu_ota_runner.package import DtuOtaPackage, PackageError, ota_command_bytes
from updater.common.firmware_manifest import FirmwareManifest


class FakeAdb:
    def __init__(self):
        self.commands = []
        self.files = {}

    def shell(self, command, check=True):
        self.commands.append((command, check))
        if command.startswith("cat '") and command.endswith("/status.json'"):
            run_id = command.split("/runs/", 1)[1].split("/", 1)[0]
            return json.dumps({
                "schema": "foxair-dtu-ota-run-v1", "run_id": run_id,
                "state": "prepared", "phase": "dry-run-complete", "terminal": False,
                "updated_at": 1, "transfer_started": False,
                "original_service_authoritative": False, "abort_allowed": True,
                "recovery": "not-required",
            })
        if "last_run_id" in command and command.startswith("cat "):
            return "run-1"
        return ""

    def push(self, local, remote):
        self.files[remote] = Path(local).read_bytes()


class DtuOtaPackageTests(unittest.TestCase):
    def make_inputs(self, root: Path):
        firmware = root / "FW3.4.bin"
        firmware.write_bytes(b"safe-test-firmware")
        hook = root / "runtime_hook"
        hook.write_text("hook")
        runner = root / "runner.sh"
        runner.write_text("runner")
        manifest = FirmwareManifest(
            schema="foxair-firmware-v1", firmware_file=firmware.name,
            software_code="82400644", display_version="V3.4", wire_version="0034",
            target_ssid="0063", size=firmware.stat().st_size,
            md5=hashlib.md5(firmware.read_bytes()).hexdigest().upper(),
            sha256=hashlib.sha256(firmware.read_bytes()).hexdigest().upper(),
            image_base="0x08050000",
        )
        return firmware, hook, runner, manifest

    def test_package_pins_every_uploaded_executable_and_command(self):
        with tempfile.TemporaryDirectory() as temp:
            firmware, hook, runner, manifest = self.make_inputs(Path(temp))
            package = DtuOtaPackage.build(
                run_id="run-1", manifest=manifest, firmware=firmware,
                hook=hook, supervisor=runner, restart_service_before_update=True,
            )
            value = package.value
            self.assertEqual(value["firmware_sha256"], manifest.sha256)
            self.assertEqual(value["command_sha256"], hashlib.sha256(ota_command_bytes(manifest)).hexdigest().upper())
            self.assertEqual(value["hook_sha256"], hashlib.sha256(hook.read_bytes()).hexdigest().upper())
            self.assertEqual(value["runner_sha256"], hashlib.sha256(runner.read_bytes()).hexdigest().upper())
            self.assertTrue(value["restart_service_before_update"])
            self.assertEqual(json.loads(package.canonical_bytes()), value)

    def test_package_rejects_unsafe_target_and_bad_run_id(self):
        with tempfile.TemporaryDirectory() as temp:
            firmware, hook, runner, manifest = self.make_inputs(Path(temp))
            with self.assertRaises(PackageError):
                DtuOtaPackage.build(
                    run_id="../bad", manifest=manifest, firmware=firmware,
                    hook=hook, supervisor=runner,
                )
            package = DtuOtaPackage.build(
                run_id="ok", manifest=manifest, firmware=firmware,
                hook=hook, supervisor=runner,
            )
            package.value["target_ssid"] = "0001"
            with self.assertRaises(PackageError):
                package.validate()

    def test_status_contract_rejects_wrong_run(self):
        adb = FakeAdb()
        client = DtuOtaClient(adb)
        valid = client.status("run-1", reconcile=False)
        self.assertEqual(valid["phase"], "dry-run-complete")
        original = adb.shell

        def wrong(command, check=True):
            if command.startswith("cat '"):
                value = valid.copy()
                value["run_id"] = "other"
                return json.dumps(value)
            return original(command, check)

        adb.shell = wrong
        with self.assertRaises(RunnerClientError):
            client.status("run-1", reconcile=False)


if __name__ == "__main__":
    unittest.main()
