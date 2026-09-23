import hashlib
import json
import subprocess
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

from updater.dtu_ota.client import DtuOtaClient, RunnerClientError
from updater.dtu_ota.package import (
    DtuOtaPackage, PackageError, ota_command_bytes, shell_payload_bytes,
)
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

    def test_shell_payloads_are_normalized_before_hash_and_upload(self):
        with tempfile.TemporaryDirectory() as temp:
            firmware, hook, runner, manifest = self.make_inputs(Path(temp))
            hook.write_bytes(b"#!/bin/sh\r\nset -eu\r\n")
            runner.write_bytes(b"#!/bin/sh\r\necho runner\r\n")
            manifest_path = Path(temp) / "FW3.4.json"
            manifest_path.write_text(json.dumps(asdict(manifest)), encoding="utf-8")
            adb = FakeAdb()
            client = DtuOtaClient(adb, source_root=Path(temp))
            client.hook = hook
            client.supervisor = runner
            client.prepare(
                manifest_path=manifest_path, firmware_path=firmware, run_id="lf-test",
            )
            uploaded_hook = adb.files["/data/foxair_ota_runner/runs/lf-test/payload/runtime_hook"]
            uploaded_runner = adb.files["/data/foxair_ota_runner/runs/lf-test/payload/dtu_ota_supervisor.sh"]
            self.assertNotIn(b"\r", uploaded_hook)
            self.assertNotIn(b"\r", uploaded_runner)
            package = json.loads(
                adb.files["/data/foxair_ota_runner/runs/lf-test/package.json"]
            )
            self.assertEqual(
                package["hook_sha256"], hashlib.sha256(uploaded_hook).hexdigest().upper()
            )
            self.assertEqual(
                package["runner_sha256"], hashlib.sha256(uploaded_runner).hexdigest().upper()
            )
            self.assertEqual(shell_payload_bytes(hook), uploaded_hook)

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
            with self.assertRaises(RunnerClientError):
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
            with self.assertRaises(RunnerClientError):
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

    def test_work_qemu_provides_persisted_progress_busybox_applets(self):
        source = Path(
            "tools/testvm/fake_adb/qemu_work_lab_backend.py"
        ).read_text(encoding="utf-8")
        ensure = source.split("def _ensure_rootfs_busybox", 1)[1].split(
            "def _remove_rootfs_busybox_overlay", 1
        )[0]
        for applet in ("od", "tr", "wc"):
            self.assertIn(f'"{applet}"', ensure)

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
        with (
            mock.patch.object(qemu_work_lab_backend, "_ota_restart_blocked", return_value=False),
            mock.patch.object(qemu_work_lab_backend, "_schedule_idle_service_restart") as restart,
        ):
            observed = qemu_work_lab_backend._service_watchdog_transition((), (4100,))
            self.assertEqual(observed, (4100,))
            observed = qemu_work_lab_backend._service_watchdog_transition(observed, ())
            self.assertEqual(observed, ())
            restart.assert_called_once_with((4100,))

        # During a real OTA the production helloworld watchdogs are paused.
        # Simulator infrastructure must therefore not hide a phnixIot4G crash.
        with (
            mock.patch.object(qemu_work_lab_backend, "_ota_restart_blocked", return_value=True),
            mock.patch.object(qemu_work_lab_backend, "_schedule_idle_service_restart") as restart,
        ):
            observed = qemu_work_lab_backend._service_watchdog_transition((4150,), ())
            self.assertEqual(observed, ())
            restart.assert_not_called()

        qemu_work_lab_backend._INTENTIONAL_RUNNER_STOP.set()
        try:
            with (
                mock.patch.object(qemu_work_lab_backend, "_ota_restart_blocked", return_value=False),
                mock.patch.object(qemu_work_lab_backend, "_schedule_idle_service_restart") as restart,
            ):
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
            "recovery_attempts", "resume_baseline_offset",
        ):
            self.assertIn(f'"{field}"', runner)
        self.assertIn("mqtt_guard_active", runner)

    def test_resume_path_is_direct_minimal_and_non_destructive(self):
        runner = Path("updater/dtu_ota/payload/dtu_ota_supervisor.sh").read_text(
            encoding="utf-8"
        )
        direct = runner.split("start_service_direct() {", 1)[1].split(
            "start_resume_hook() {", 1
        )[0]
        recovery = runner.split("recover_after_hook_loss() {", 1)[1].split(
            "start_http() {", 1
        )[0]
        self.assertIn("exec ./phnixIot4G", direct)
        self.assertNotIn("resume_watchdogs", direct)
        self.assertIn("RECOVERY_MAX_ATTEMPTS=3", runner)
        self.assertIn("RESUME_BASELINE_OFFSET=$OFFSET", recovery)
        self.assertIn('test "$OFFSET" -gt "$RESUME_BASELINE_OFFSET"', recovery)
        self.assertIn("/cache/phnixIot_device_OTA", recovery)
        self.assertNotIn("cp /cache/phnixIot_device_OTA", recovery)

        hook = Path("updater/dtu_ota/payload/phnix_ota_runtime_hook").read_text(
            encoding="utf-8"
        )
        resume = hook.split("\nresume_hook() {\n", 1)[1].split("\nhold_hook() {\n", 1)[0]
        shared_gdb = hook.split("make_gdb_script() {", 1)[1].split("run_hook() {", 1)[0]
        self.assertNotIn("backup_persistent_state", resume)
        self.assertNotIn("restore_persistent_state", resume)
        self.assertIn("RESUME_MODE", shared_gdb)
        self.assertIn("resume-wait-mainboard", shared_gdb)
        self.assertIn("break *0x1ba04", shared_gdb)
        self.assertIn("set \\$r0 = 11", shared_gdb)

    def test_windows_maps_productive_runner_phases_to_friendly_text(self):
        gui = Path("updater/windows/foxair_updater_runner_gui.py").read_text(
            encoding="utf-8"
        )
        enduser = Path("updater/windows/foxair_updater_runner_enduser.py").read_text(
            encoding="utf-8"
        )
        for phase in (
            "service-restart-wait",
            "service-restart-verified",
            "service-ready-wait",
            "service-ready",
            "post-restart-preflight",
            "failure-report",
            "precondition-rejected",
            "parser-rejected",
            "c36e-rejected",
            "debugger-ended-before-terminal",
            "debugger-unexpected-stop",
            "runner-lost",
            "recovery-required",
            "same-version-restore",
            "backup",
        ):
            self.assertIn(f'"{phase}":', gui)
        self.assertIn('"service-ready-wait": (', enduser)
        self.assertIn('"runner-lost": (', enduser)
        supervisor = Path("updater/dtu_ota/payload/dtu_ota_supervisor.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("RECOVERY_RESUME_TIMEOUT=1200", supervisor)

    def test_c5a8_stall_watchdog_reuses_resume_path_without_extra_polling(self):
        runner = Path("updater/dtu_ota/payload/dtu_ota_supervisor.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("C5A8_STALL_TIMEOUT=1200", runner)
        self.assertIn("C5A8_STALL_LAST_OFFSET=0", runner)
        self.assertIn("C5A8_STALL_ELAPSED=0", runner)

        main_loop = runner.split("post_abort_logged=0", 1)[1].split(
            "classify_action() {", 1
        )[0]
        stall_logic = main_loop.split(
            "# No extra modem polling:", 1
        )[1].split('detail="Autonomous DTU OTA is running."', 1)[0]
        self.assertIn(
            'C5A8_STALL_ELAPSED=$((C5A8_STALL_ELAPSED + 2))',
            stall_logic,
        )
        self.assertIn(
            'if test "$OFFSET" -gt "$C5A8_STALL_LAST_OFFSET"; then',
            stall_logic,
        )
        self.assertIn("recover_after_transfer_stall", stall_logic)
        self.assertNotIn("refresh_progress", stall_logic)

        recovery = runner.split("recover_after_transfer_stall() {", 1)[1].split(
            "recover_after_hook_loss() {", 1
        )[0]
        self.assertIn(
            'test "$RECOVERY_ATTEMPTS" -lt "$RECOVERY_MAX_ATTEMPTS"',
            recovery,
        )
        self.assertIn('kill -KILL "$SERVICE_PID"', recovery)
        self.assertIn("recover_after_hook_loss", recovery)
        self.assertIn("transfer_stalled", recovery)

        enduser = Path("updater/windows/foxair_updater_runner_enduser.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('reason == "transfer_stalled"', enduser)

    def test_recovery_deadline_is_exported_once_and_counted_down_only_on_windows(self):
        runner = Path("updater/dtu_ota/payload/dtu_ota_supervisor.sh").read_text(
            encoding="utf-8"
        )
        recovery = runner.split("recover_after_hook_loss() {", 1)[1].split(
            "start_http() {", 1
        )[0]
        self.assertIn('"recovery_deadline_at":%s', runner)
        self.assertIn("RECOVERY_DEADLINE_AT=0", runner)
        self.assertIn(
            'RECOVERY_DEADLINE_AT=$(( $(date +%s) + RECOVERY_RESUME_TIMEOUT ))',
            recovery,
        )
        self.assertLess(
            recovery.index("RECOVERY_DEADLINE_AT=$(("),
            recovery.index('while test "$elapsed" -lt "$RECOVERY_RESUME_TIMEOUT"'),
        )

        enduser = Path("updater/windows/foxair_updater_runner_enduser.py").read_text(
            encoding="utf-8"
        )
        countdown = enduser.split("def _update_recovery_countdown", 1)[1].split(
            "def _sync_runner_elapsed", 1
        )[0]
        self.assertIn("setInterval(1000)", enduser)
        self.assertIn("recovery_deadline_at", countdown)
        self.assertNotIn("_run_runner(", countdown)
        self.assertNotIn("_poll_runner_status(", countdown)

    def test_windows_completes_transient_flow_warnings_after_next_step(self):
        enduser = Path("updater/windows/foxair_updater_runner_enduser.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'if phase not in {"hook-starting", "attaching"}:',
            enduser,
        )
        self.assertIn(
            'current = self._flow_steps.get("runner-yield")',
            enduser,
        )

    def test_runner_shell_payloads_parse_with_posix_sh(self):
        for path in (
            Path("updater/dtu_ota/payload/dtu_ota_supervisor.sh"),
            Path("updater/dtu_ota/payload/phnix_ota_runtime_hook"),
        ):
            result = subprocess.run(
                ["sh", "-n", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{path}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
