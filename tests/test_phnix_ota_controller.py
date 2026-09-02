import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock

from tools.phnix_ota import phnix_local_ota_controller as controller
from tools.phnix_ota.phnix_local_ota_controller import (
    AdbMonitorRecovery,
    cancel_proof_ok,
    cancel_payload,
    build_parser,
    OtaError,
    command_payload,
    crc16_x25,
    parse_ota_info,
    pre_c5a8_proof_ok,
    same_version_proof_ok,
    validate_logger_checklist,
    remote_status,
    restore_original_runtime,
    mqtt_tcp_established,
    passive_helper_exit_is_safe,
    passive_adb_detach_is_safe,
    passive_recovery_is_plausible,
)
from updater.common.firmware_manifest import FirmwareManifest

TEST_SIZE = 287_598
TEST_MD5 = "CEB6A4BF386FF644E23E410023E74673"


def test_manifest():
    return FirmwareManifest(
        schema="foxair-firmware-v1", firmware_file="FW3.3.bin",
        software_code="82400644", display_version="V3.3",
        wire_version="0033", target_ssid="0063", size=TEST_SIZE,
        md5=TEST_MD5, sha256="A" * 64, image_base="0x08050000",
    )


class OtaInfoTests(unittest.TestCase):
    def test_permanent_adb_loss_detaches_only_after_authoritative_grace(self):
        self.assertTrue(passive_adb_detach_is_safe(
            grace_expired=True, transfer_started=True,
            original_service_authoritative=True,
        ))
        self.assertFalse(passive_adb_detach_is_safe(
            grace_expired=False, transfer_started=True,
            original_service_authoritative=True,
        ))

    def test_adb_loss_before_authoritative_transfer_does_not_detach(self):
        self.assertFalse(passive_adb_detach_is_safe(
            grace_expired=True, transfer_started=False,
            original_service_authoritative=False,
        ))

    def test_passive_recovery_same_service_and_forward_offset(self):
        self.assertTrue(passive_recovery_is_plausible(
            transfer_started=True, original_service_authoritative=True,
            previous_pid="1322", recovered_pid="1322",
            previous_offset=89376, recovered_offset=120288,
        ))

    def test_helper_exit_after_confirmed_loss_is_not_firmware_error(self):
        self.assertTrue(passive_helper_exit_is_safe(
            passive_monitoring=True, monitoring_was_lost=True,
            transfer_started=True, original_service_authoritative=True,
            returncode=0,
        ))

    def test_helper_exit_before_authoritative_transfer_remains_error(self):
        self.assertFalse(passive_helper_exit_is_safe(
            passive_monitoring=False, monitoring_was_lost=False,
            transfer_started=False, original_service_authoritative=False,
            returncode=0,
        ))

    def test_nonzero_helper_exit_remains_error_after_monitoring_loss(self):
        self.assertFalse(passive_helper_exit_is_safe(
            passive_monitoring=True, monitoring_was_lost=True,
            transfer_started=True, original_service_authoritative=True,
            returncode=1,
        ))
    def test_adb_monitor_requires_failure_count_and_grace_period(self):
        recovery = AdbMonitorRecovery(generation=object())
        self.assertFalse(recovery.failed(100.0))
        for now in (102.0, 104.0, 106.0):
            self.assertFalse(recovery.failed(now))
        self.assertEqual(recovery.fail_count, 4)
        self.assertFalse(recovery.failed(110.0))

        too_few = AdbMonitorRecovery(generation=object())
        for now in (100.0, 115.0, 131.0):
            self.assertFalse(too_few.failed(now))
        self.assertTrue(too_few.recovering)

        threshold = AdbMonitorRecovery(generation=object())
        for now in (100.0, 105.0, 110.0, 120.0):
            self.assertFalse(threshold.failed(now))
        self.assertTrue(threshold.failed(130.0))

    def test_adb_monitor_success_and_new_generation_reset_recovery(self):
        generation = object()
        recovery = AdbMonitorRecovery(generation=generation)
        recovery.failed(100.0)
        recovery.recovered()
        self.assertEqual(recovery.fail_count, 0)
        self.assertIsNone(recovery.first_failure_time)
        self.assertFalse(recovery.recovering)

        next_run = AdbMonitorRecovery(generation=object())
        self.assertIsNot(next_run.generation, generation)
        self.assertEqual(next_run.fail_count, 0)

    def test_mqtt_preflight_requires_tcp_established(self):
        self.assertFalse(mqtt_tcp_established("tcp 0 1 10.0.0.2:1234 1.2.3.4:1883 SYN_SENT"))
        self.assertFalse(mqtt_tcp_established("tcp 0 0 0.0.0.0:1883 0.0.0.0:* LISTEN"))
        self.assertTrue(mqtt_tcp_established("tcp 0 0 10.0.0.2:4567 1.2.3.4:1883 ESTABLISHED"))

    def make_info(self) -> bytearray:
        raw = bytearray(220)
        raw[28:34] = b"V1.2\0\0"
        raw[165:198] = TEST_MD5.encode("ascii") + b"\0"
        raw[198:207] = b"82400644\0"
        raw[207:212] = b"0033\0"
        raw[212:216] = (168).to_bytes(4, "little")
        raw[216:220] = TEST_SIZE.to_bytes(4, "little")
        raw[0:4] = crc16_x25(raw[4:220]).to_bytes(4, "little")
        return raw

    def test_parses_crc_and_fw33_metadata(self):
        info = parse_ota_info(bytes(self.make_info()))
        self.assertTrue(info.crc_ok)
        self.assertEqual(info.md5, TEST_MD5)
        self.assertEqual(info.software_code, "82400644")
        self.assertEqual(info.software_version, "0033")
        self.assertEqual(info.offset, 168)
        self.assertEqual(info.length, TEST_SIZE)

    def test_detects_corruption(self):
        raw = self.make_info()
        raw[100] ^= 0x01
        self.assertFalse(parse_ota_info(bytes(raw)).crc_ok)

    def test_0033_is_protocol_code_not_version_field(self):
        payload = command_payload("http://127.0.0.1:8081/phnixIot_device_OTA.bin", test_manifest())
        self.assertEqual(payload["code"], "0033")
        self.assertEqual(payload["param"]["softwareVer"], "V3.3")

    def test_cancel_requires_complete_terminal_proof(self):
        proof = {
            "phase": "cancelled",
            "terminal": True,
            "c36a_sent": True,
            "c36c_status": 1,
            "cancel_pending": False,
            "board_ota_step": 12,
            "normal_operation_verified": True,
        }
        self.assertTrue(cancel_proof_ok(proof))
        for field in ("c36a_sent", "cancel_pending", "normal_operation_verified"):
            broken = dict(proof)
            broken.pop(field)
            self.assertFalse(cancel_proof_ok(broken))
        for field in ("c36c_status", "board_ota_step"):
            broken = dict(proof)
            broken[field] = 0
            self.assertFalse(cancel_proof_ok(broken))

    def test_cancel_payload_uses_original_0073_dispatch(self):
        self.assertEqual(cancel_payload(), {"cmd": "CMD_OTA", "code": "0073"})

    def test_pre_c5a8_proof_requires_zero_firmware_frames(self):
        hook = {
            "phase": "pre-c5a8-hold", "terminal": True,
            "c350_sent": True, "c36e_status_1": True,
            "c357_sent": True, "c36e_status_2": True,
            "c5a8_sent": False, "board_ota_step": 1,
        }
        trace = {"c5a8_frames": 0, "metadata_stable": True, "ssid_match": True}
        self.assertTrue(pre_c5a8_proof_ok(hook, trace))
        trace["c5a8_frames"] = 1
        self.assertFalse(pre_c5a8_proof_ok(hook, trace))

    def test_logger_checklist_is_fail_closed(self):
        checklist = {
            "schema": "phnix-pre-c5a8-logger-v1",
            "capture_started": True, "passive_only": True,
            "raw_hex_enabled": True, "timestamps_enabled": True,
            "crc_validation_enabled": True,
            "fragment_reassembly_enabled": True,
            "multi_frame_split_enabled": True, "secrets_masked": True,
            "c5a8_critical_alarm_enabled": True,
            "registers": ["C350", "C357", "C36E", "C36A", "C36C", "C5A8"],
            "output_file": "capture.log",
        }
        self.assertEqual(validate_logger_checklist(checklist), [])
        checklist["passive_only"] = False
        checklist["registers"].remove("C5A8")
        blockers = validate_logger_checklist(checklist)
        self.assertTrue(any("passive_only" in item for item in blockers))
        self.assertTrue(any("C5A8" in item for item in blockers))

    def test_same_version_proof_is_fail_closed(self):
        proof = {
            "phase": "c350-same-version", "terminal": True,
            "c350_sent": True, "c36e_status": 0, "ssid_match": True,
            "c357_sent": False, "c5a8_sent": False,
            "state_restored": True, "recovery_required": False,
        }
        self.assertTrue(same_version_proof_ok(proof))
        for field in ("c350_sent", "ssid_match", "state_restored"):
            broken = dict(proof)
            broken[field] = False
            self.assertFalse(same_version_proof_ok(broken))
        for field in ("c357_sent", "c5a8_sent", "recovery_required"):
            broken = dict(proof)
            broken[field] = True
            self.assertFalse(same_version_proof_ok(broken))
        broken = dict(proof, c36e_status=1)
        self.assertFalse(same_version_proof_ok(broken))

    def test_status_reader_uses_last_complete_json_record(self):
        adb = Mock()
        adb.shell.return_value = '{"phase":"old"}\n{"phase":"new"}'
        adb.read_file.return_value = bytes(self.make_info())
        self.assertEqual(remote_status(adb)["hook"]["phase"], "new")

    def test_human_progress_uses_verified_offset_and_suppresses_duplicates(self):
        controller.COLOR_ENABLED = False
        controller._LAST_HUMAN_PHASE = None
        controller._LAST_HUMAN_PERCENT = -1
        controller._LAST_HUMAN_PROGRESS_AT = 0.0
        output = io.StringIO()
        with redirect_stdout(output):
            controller._human_event("status", {
                "hook": {"phase": "c5a8"},
                "ota_info": {"crc_ok": True, "offset": 71_899, "length": TEST_SIZE},
            })
            controller._human_event("status", {
                "hook": {"phase": "c5a8"},
                "ota_info": {"crc_ok": True, "offset": 71_899, "length": TEST_SIZE},
            })
            controller._human_event("status", {
                "hook": {"phase": "c5a8"},
                "ota_info": {"crc_ok": True, "offset": 74_776, "length": TEST_SIZE},
            })
        rendered = output.getvalue()
        self.assertEqual(rendered.count("Fortschritt:"), 2)
        self.assertIn("25 % (71.899 / 287.598 Byte)", rendered)
        self.assertIn("26 % (74.776 / 287.598 Byte)", rendered)

    def test_run_maintenance_switches_do_not_require_manifest(self):
        check = build_parser().parse_args(["run", "--check", "status"])
        restore = build_parser().parse_args(["run", "--restore", "original"])
        self.assertEqual(check.check, "status")
        self.assertIsNone(check.manifest)
        self.assertEqual(restore.restore, "original")
        self.assertIsNone(restore.manifest)

    def test_full_update_keeps_mqtt_connected_by_default(self):
        default = build_parser().parse_args(["run", "--manifest", "FW3.4.json"])
        isolated = build_parser().parse_args([
            "run", "--manifest", "FW3.4.json", "--isolate-mqtt",
        ])
        alias = build_parser().parse_args([
            "run", "--manifest", "FW3.4.json", "--update-no-mqtt",
        ])
        self.assertFalse(default.isolate_mqtt)
        self.assertTrue(isolated.isolate_mqtt)
        self.assertTrue(alias.isolate_mqtt)

    def test_runtime_hook_only_blocks_mqtt_when_requested(self):
        hook = Path("updater/dtu_ota/payload/phnix_ota_runtime_hook").read_text(encoding="utf-8")
        run = hook.split("run_hook() {", 1)[1].split("hold_hook() {", 1)[0]
        self.assertIn('if test "$ISOLATE_MQTT" = 1; then', run)
        self.assertIn("--dport 1883", run)
        self.assertIn("--sport 1883", run)

    def test_full_runtime_hook_uses_proven_yield_loop_and_transfer_marker(self):
        hook = Path("updater/dtu_ota/payload/phnix_ota_runtime_hook").read_text(encoding="utf-8")
        full = hook.split("make_gdb_script() {", 1)[1].split("run_hook() {", 1)[0]
        self.assertIn("break *0x1fe40", full)
        self.assertNotIn("break *0x1fdac", full)
        self.assertIn("*(unsigned int *)0x930dc != 0", full)
        self.assertIn("*(unsigned char *)0x98a94 != 12", full)
        self.assertIn("shell touch $TRANSFER_STARTED", full)
        self.assertIn("shell touch $INJECTION_STARTED", full)
        self.assertIn(r"if \$pc != 0x1c4bc", full)
        self.assertIn(r"if \$pc != 0x1ba04", full)
        self.assertIn("break *0x1ba04", full)
        self.assertIn("\"phase\":\"same-version\"", full)
        self.assertIn(r"while \$local_ota_active == 1", full)
        self.assertIn(r"set \$ota_event_handled = 0", full)
        self.assertIn(r"if \$pc == 0x1cea0", full)
        self.assertIn(r"if \$pc == 0x1c7cc", full)
        self.assertNotIn("commands 3", full)
        self.assertNotIn("commands 4", full)
        self.assertNotIn("commands 5", full)
        self.assertIn("\"phase\":\"debugger-unexpected-stop\"", full)

    def test_full_runtime_hook_rejects_clean_debugger_exit_before_terminal_state(self):
        hook = Path("updater/dtu_ota/payload/phnix_ota_runtime_hook").read_text(encoding="utf-8")
        run = hook.split("run_hook() {", 1)[1].split("hold_hook() {", 1)[0]
        self.assertIn('GDB_RC=0', run)
        self.assertIn('grep -q \'"terminal":true\' "$STATUS"', run)
        self.assertIn("\"phase\":\"debugger-ended-before-terminal\"", run)

    def test_cleanup_does_not_stop_original_service_after_ota_acceptance(self):
        hook = Path("updater/dtu_ota/payload/phnix_ota_runtime_hook").read_text(encoding="utf-8")
        cleanup = hook.split("cleanup() {", 1)[1].split("stop_hook() {", 1)[0]
        authoritative = cleanup.split('if test -f "$ORIGINAL_SERVICE_OWNS"; then', 1)[1].split("else", 1)[0]
        self.assertIn('kill -CONT "$PID"', authoritative)
        self.assertNotIn('kill -STOP "$PID"', authoritative)
        self.assertIn("\"phase\":\"original-service-active-unmonitored\"", authoritative)

    def test_restore_refuses_after_firmware_blocks_started(self):
        adb = Mock()
        adb.shell.return_value = "0"
        with self.assertRaises(OtaError):
            restore_original_runtime(adb, Path("updater/dtu_ota/payload/phnix_ota_runtime_hook"))
        self.assertEqual(adb.shell.call_count, 2)

    def test_injected_restore_kills_old_service_without_resuming_it(self):
        hook = Path("updater/dtu_ota/payload/phnix_ota_runtime_hook").read_text(encoding="utf-8")
        restore = hook.split("restore_original_hook() {", 1)[1].split("attach_test() {", 1)[0]
        injected = restore.split('if test "$INJECTED" = 1; then', 1)[1].split("\n    fi", 1)[0]
        self.assertIn('kill -KILL "$OLD_PID"', injected)
        self.assertNotIn('kill -CONT "$OLD_PID"', injected)

    def test_bundled_runtime_helper_matches_verified_build(self):
        digest = controller.validate_local_runtime_helper(
            Path("updater/dtu_ota/payload/phnix_ota_runtime_hook")
        )
        self.assertEqual(len(digest), 64)


if __name__ == "__main__":
    unittest.main()
