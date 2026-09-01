import hashlib
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from tools.dtu_ota_runner.client import DtuOtaClient, RunnerClientError
from tools.dtu_ota_runner.package import DtuOtaPackage, PackageError, ota_command_bytes
from tools.testvm.fake_adb import qemu_work_lab_backend
from tools.testvm.work_lab.rs485_fault_emulator import (
    board_software_info_frame,
    crc16_modbus,
    resolve_staged_firmware,
)
from updater.common.adb_transport import TransportError
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
        if "active.lock/run_id" in command and command.startswith("cat "):
            return ""
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

    def test_active_run_is_independent_from_stale_last_run(self):
        adb = FakeAdb()
        client = DtuOtaClient(adb)
        self.assertIsNone(client.active_run_id())
        self.assertEqual(client.current_run_id(), "run-1")

    def test_prepare_reports_persisted_preflight_reason(self):
        with tempfile.TemporaryDirectory() as temp:
            firmware, hook, runner, manifest = self.make_inputs(Path(temp))
            manifest_path = Path(temp) / "FW3.4.json"
            manifest_path.write_text(json.dumps(asdict(manifest)), encoding="utf-8")
            adb = FakeAdb()
            original = adb.shell

            def rejected(command, check=True):
                if " preflight 'run-rejected'" in command:
                    raise TransportError("empty adb error")
                if command.startswith("cat '") and command.endswith("/status.json'"):
                    return json.dumps({
                        "schema": "foxair-dtu-ota-run-v1", "run_id": "run-rejected",
                        "state": "failed", "phase": "package-preflight", "terminal": True,
                        "updated_at": 1, "transfer_started": False,
                        "original_service_authoritative": False, "abort_allowed": True,
                        "recovery": "not-required", "reason": "package_validation_failed",
                        "detail": "DTU package validation failed with code 72 before any service action.",
                    })
                return original(command, check)

            adb.shell = rejected
            client = DtuOtaClient(adb, source_root=Path(temp))
            client.hook = hook
            client.supervisor = runner
            with self.assertRaisesRegex(RunnerClientError, "code 72"):
                client.prepare(
                    manifest_path=manifest_path, firmware_path=firmware,
                    run_id="run-rejected",
                )

    def test_board_peer_resolves_content_pinned_runner_firmware(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "rootfs"
            legacy = root / "data/phnix_local_ota/phnixIot_device_OTA.bin"
            staged = root / "data/foxair_ota_runner/runs/run-1/payload/firmware.bin"
            staged.parent.mkdir(parents=True)
            payload = b"new-autonomous-runner-image"
            staged.write_bytes(payload)
            actual = resolve_staged_firmware(
                str(legacy), len(payload), hashlib.md5(payload).hexdigest(),
            )
            self.assertEqual(actual, payload)

    def test_restart_at_half_preserves_only_proven_resume_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data"
            data.mkdir()
            info = bytearray(220)
            info[212:216] = (145000).to_bytes(4, "little")
            info[216:220] = (289806).to_bytes(4, "little")
            (data / "phnixIot_device_OTA_INFO").write_bytes(info)
            (data / "foxair_board_ota_resume.json").write_text('{"next_block":864}')
            original = qemu_work_lab_backend.root_path
            qemu_work_lab_backend.root_path = lambda remote: root / remote.lstrip("/")
            try:
                state = {"scenario": "restart-at-50-resume"}
                self.assertTrue(qemu_work_lab_backend._resume_restart_ready(
                    "scenario", "restart-at-50-resume", state,
                ))
                self.assertFalse(qemu_work_lab_backend._resume_restart_ready(
                    "scenario", "success", state,
                ))
                (data / "foxair_board_ota_resume.json").unlink()
                self.assertFalse(qemu_work_lab_backend._resume_restart_ready(
                    "scenario", "restart-at-50-resume", state,
                ))
            finally:
                qemu_work_lab_backend.root_path = original

    def test_resume_software_info_frame_matches_live_c544_layout(self):
        frame = board_software_info_frame("0033")
        self.assertEqual(frame[:7], bytes.fromhex("63 10 C5 44 00 0D 1A"))
        self.assertEqual(frame[7:9], bytes.fromhex("00 63"))
        self.assertEqual(frame[9:17], b"82300314")
        self.assertEqual(frame[17:21], b"0000")
        self.assertEqual(frame[21:29], b"82400644")
        self.assertEqual(frame[29:33], b"0033")
        self.assertEqual(frame[-2:], crc16_modbus(frame[:-2]))


if __name__ == "__main__":
    unittest.main()
