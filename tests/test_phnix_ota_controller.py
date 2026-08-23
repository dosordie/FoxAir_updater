import unittest
from unittest.mock import Mock

from tools.phnix_ota.phnix_local_ota_controller import (
    cancel_proof_ok,
    cancel_payload,
    command_payload,
    crc16_x25,
    parse_ota_info,
    pre_c5a8_proof_ok,
    same_version_proof_ok,
    validate_logger_checklist,
    remote_status,
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


if __name__ == "__main__":
    unittest.main()
