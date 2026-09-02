import hashlib
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

from updater.dtu_ota.client import DtuOtaClient, RunnerClientError
from updater.dtu_ota.package import DtuOtaPackage, PackageError, ota_command_bytes
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
        self.active = ""

    def shell(self, command, check=True):
        self.commands.append((command, check))
        if command.startswith("cat '") and "/status.json'" in command:
            run_id = command.split("/runs/", 1)[1].split("/", 1)[0]
            return json.dumps({
                "schema": "foxair-dtu-ota-run-v1", "run_id": run_id,
                "state": "prepared", "phase": "dry-run-complete", "terminal": False,
                "updated_at": 1, "transfer_started": False,
                "original_service_authoritative": False, "abort_allowed": True,
                "recovery": "not-required",
                "service_restart_requested": False, "service_restart_verified": False,
                "mqtt_isolation_requested": False, "mqtt_isolated": False,
                "boot_id": "boot-test",
            })
        if "last_run_id" in command and command.startswith("cat "):
            return "run-1"
        if "active.lock/run_id" in command and command.startswith("cat "):
            return self.active
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

    def test_current_prefers_plausible_active_run(self):
        adb = FakeAdb()
        adb.active = "active-2"
        client = DtuOtaClient(adb)
        self.assertEqual(client.current_run_id(), "active-2")

    def test_prepare_is_side_effect_free_while_active_run_exists(self):
        with tempfile.TemporaryDirectory() as temp:
            firmware, _, _, manifest = self.make_inputs(Path(temp))
            manifest_path = Path(temp) / "FW3.4.json"
            manifest_path.write_text(json.dumps(asdict(manifest)), encoding="utf-8")
            adb = FakeAdb()
            adb.active = "active-2"
            client = DtuOtaClient(adb)
            with self.assertRaisesRegex(RunnerClientError, "active-2"):
                client.prepare(manifest_path=manifest_path, firmware_path=firmware)
            self.assertEqual(adb.files, {})

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
                        "service_restart_requested": False, "service_restart_verified": False,
                        "mqtt_isolation_requested": False, "mqtt_isolated": False,
                        "boot_id": "boot-test",
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

    def test_qemu_watchdog_restarts_only_after_external_service_death(self):
        with mock.patch.object(
            qemu_work_lab_backend, "_schedule_idle_service_restart",
        ) as restart:
            observed = qemu_work_lab_backend._service_watchdog_transition((), (4100,))
            self.assertEqual(observed, (4100,))
            observed = qemu_work_lab_backend._service_watchdog_transition(observed, ())
            self.assertEqual(observed, ())
            restart.assert_called_once_with((4100,))

        qemu_work_lab_backend._INTENTIONAL_RUNNER_STOP.set()
        try:
            with mock.patch.object(
                qemu_work_lab_backend, "_schedule_idle_service_restart",
            ) as restart:
                observed = qemu_work_lab_backend._service_watchdog_transition((4200,), ())
                self.assertEqual(observed, ())
                restart.assert_not_called()
        finally:
            qemu_work_lab_backend._INTENTIONAL_RUNNER_STOP.clear()

    def test_qemu_runtime_hook_injects_inside_yield_breakpoint_commands(self):
        hook = Path("updater/dtu_ota/payload/phnix_ota_runtime_hook").read_text(encoding="utf-8")
        qemu = hook.split("SIGFPE_POLICY=nopass", 1)[1].split("else\n", 1)[0]
        commands = qemu.split("commands 1", 1)[1].split("end\n", 1)[0]
        self.assertIn('set {char[512]} 0x94ab4 = "$ESCAPED"', commands)
        self.assertIn("set \\$pc = 0x19958", commands)
        self.assertIn("continue", commands)
        self.assertIn("commands 2", qemu)

    def test_runner_p0_guards_are_persistent_and_side_effect_free(self):
        runner = Path("updater/dtu_ota/payload/dtu_ota_supervisor.sh").read_text(
            encoding="utf-8"
        )
        terminal = runner.split("terminal_result() {", 1)[1].split("guarded_result() {", 1)[0]
        guarded = runner.split("guarded_result() {", 1)[1].split("runner_identity() {", 1)[0]
        run = runner.split("run_action() {", 1)[1].split("classify_action() {", 1)[0]
        classify = runner.split("classify_action() {", 1)[1].split("ack_action() {", 1)[0]
        self.assertNotIn('write_status "$state" "$phase" true "$reason" "$detail" || true', terminal)
        self.assertNotIn("release_lock", guarded)
        self.assertNotIn("stop_http", guarded)
        self.assertLess(run.index('status_string state'), run.index("acquire_lock"))
        self.assertIn("restore_original_confirmed", run)
        authority = classify.split('if test "$TRANSFER_STARTED" = true', 1)[1].split("else", 1)[0]
        self.assertNotIn("rm -f \"$LOCK", authority)
        self.assertIn("boot_fingerprint", classify)

    def test_runner_status_distinguishes_requested_and_verified_flags(self):
        runner = Path("updater/dtu_ota/payload/dtu_ota_supervisor.sh").read_text(
            encoding="utf-8"
        )
        for field in (
            "service_restart_requested", "service_restart_verified",
            "mqtt_isolation_requested", "mqtt_isolated", "boot_id",
        ):
            self.assertIn(f'"{field}"', runner)
        self.assertIn("mqtt_guard_active", runner)


if __name__ == "__main__":
    unittest.main()
