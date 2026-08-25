import re
import unittest

from updater.common.phnix_modem_info import (
    BOARD_HARDWARE_CODE_ADDRESS,
    BOARD_HARDWARE_VERSION_ADDRESS,
    BOARD_SOFTWARE_CODE_ADDRESS,
    BOARD_SOFTWARE_VERSION_ADDRESS,
    CELL_ID_ADDRESS,
    CURRENT_PLMN_VALID_ADDRESS,
    DEVICE_NAME_ADDRESS,
    DEVICE_NAME_SIZE,
    DEVICE_SECRET_ADDRESS,
    DEVICE_SECRET_SIZE,
    ERROR_STATUS_ADDRESS,
    ICCID_ADDRESS,
    ICCID_SIZE,
    IMEI_ADDRESS,
    IMEI_SIZE,
    IMSI_ADDRESS,
    IMSI_SIZE,
    LAC_ADDRESS,
    MCC_ADDRESS,
    MNC_ADDRESS,
    MODE_TYPE_ADDRESS,
    MQTT_CLIENT_STATE_OFFSET,
    MQTT_INIT_SIGNAL_ADDRESS,
    NETWORK_DESCRIPTION_ADDRESS,
    NETWORK_DESCRIPTION_SIZE,
    PCLIENT_POINTER_ADDRESS,
    PRODUCT_KEY_ADDRESS,
    PRODUCT_KEY_SIZE,
    PRODUCT_SECRET_ADDRESS,
    PRODUCT_SECRET_SIZE,
    ROAMING_INDICATOR_ADDRESS,
    ROAMING_VALID_ADDRESS,
    SERVING_SYSTEM_ADDRESS,
    SERVING_SYSTEM_SIZE,
    SIM_STATUS_ADDRESS,
    SIM_STATUS_SIZE,
    STATISTICS_ADDRESS,
    STATISTICS_SIZE,
    decode_statistics,
    format_seconds,
    read_phnix_modem_info,
    read_process_memory,
)


def padded(text: str, size: int) -> bytes:
    raw = text.encode("ascii")
    if len(raw) >= size:
        return raw[:size]
    return raw + b"\x00" * (size - len(raw))


class FakeAdb:
    def __init__(self, memory: dict[int, bytes], pid: str = "1234"):
        self.memory = memory
        self.pid = pid
        self.commands: list[str] = []

    def shell(self, command: str, check: bool = True) -> str:
        self.commands.append(command)
        if command == "pidof phnixIot4G":
            return self.pid

        if "dd if=/proc/" in command:
            self.assert_read_only(command)
            match = re.search(r"skip=(\d+) count=(\d+)", command)
            if not match:
                raise AssertionError(command)
            address = int(match.group(1))
            length = int(match.group(2))
            raw = self.memory.get(address, b"")[:length]
            # Simulate line-oriented adb shell text output. CR/LF around the
            # hexadecimal representation must never become memory bytes.
            groups = [raw[index:index + 16] for index in range(0, len(raw), 16)]
            return "\r\n".join(" ".join(f"{byte:02x}" for byte in group) for group in groups) + "\r\n"

        if command == "cat /proc/net/route":
            return (
                "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
                "rmnet_data0\t00000000\t68FAEC0A\t0003\t0\t0\t0\t00000000\n"
            )

        if command.startswith("ip -o -4 addr show dev rmnet_data0"):
            return "12: rmnet_data0    inet 10.236.250.103/28 brd 10.236.250.111 scope global rmnet_data0\n"
        if command.startswith("ip -o -4 addr show"):
            return "12: rmnet_data0    inet 10.236.250.103/28 brd 10.236.250.111 scope global rmnet_data0\n"

        if check:
            raise AssertionError(command)
        return ""

    @staticmethod
    def assert_read_only(command: str):
        if "dd if=/proc/" not in command or "| od -An -v -tx1" not in command:
            raise AssertionError(command)
        forbidden = (" of=", "/dev/ttyHSL2", "modbus", "FC03")
        if any(item in command for item in forbidden):
            raise AssertionError(f"unexpected active/write operation: {command}")


class PhnixModemInfoTests(unittest.TestCase):
    @staticmethod
    def _statistics_block() -> bytes:
        block = bytearray(STATISTICS_SIZE)

        def put(offset: int, value: int):
            block[offset:offset + 4] = value.to_bytes(4, "little")

        put(0x00, 19)
        put(0x04, 7)
        put(0x08, 35369446)
        put(0x14, 35376928)
        put(0x18, 588940)
        put(0x1C, 1601)
        put(0x20, 0)
        put(0x24, 6)
        put(0x28, 27)
        put(0x2C, 3)
        put(0x44, 12017)
        put(0x48, 11993)
        put(0x4C, 17)
        put(0x58, 15886)
        put(0x5C, 932)
        block[0x6C:0x78] = b"WF2210250475"
        return bytes(block)

    @staticmethod
    def _live_memory() -> dict[int, bytes]:
        pclient = 0x120000
        serving = b"".join(
            value.to_bytes(4, "little") for value in (1, 1, 1, 0, 1, 8)
        )
        sim = b"".join(value.to_bytes(4, "little") for value in (1, 3, 7))
        return {
            BOARD_SOFTWARE_CODE_ADDRESS: padded("82400644", 9),
            BOARD_SOFTWARE_VERSION_ADDRESS: padded("V3.3", 5),
            BOARD_HARDWARE_CODE_ADDRESS: padded("82300314", 9),
            BOARD_HARDWARE_VERSION_ADDRESS: padded("0000", 5),
            ICCID_ADDRESS: padded("89330123456789012345", ICCID_SIZE),
            IMSI_ADDRESS: padded("208011234567890", IMSI_SIZE),
            IMEI_ADDRESS: padded("860147123456789", IMEI_SIZE),
            MODE_TYPE_ADDRESS: bytes([2]),
            SIM_STATUS_ADDRESS: sim,
            SERVING_SYSTEM_ADDRESS: serving,
            CURRENT_PLMN_VALID_ADDRESS: bytes([1]),
            MCC_ADDRESS: (262).to_bytes(2, "little"),
            MNC_ADDRESS: (1).to_bytes(2, "little"),
            NETWORK_DESCRIPTION_ADDRESS: padded("TDG", NETWORK_DESCRIPTION_SIZE),
            ROAMING_VALID_ADDRESS: (1).to_bytes(4, "little"),
            ROAMING_INDICATOR_ADDRESS: (0).to_bytes(4, "little"),
            LAC_ADDRESS: (0xFFFE).to_bytes(2, "little"),
            CELL_ID_ADDRESS: (44867840).to_bytes(4, "little"),
            ERROR_STATUS_ADDRESS: (0).to_bytes(4, "little"),
            STATISTICS_ADDRESS: PhnixModemInfoTests._statistics_block(),
            DEVICE_NAME_ADDRESS: padded("860147123456789", DEVICE_NAME_SIZE),
            PRODUCT_KEY_ADDRESS: padded("testProductKey", PRODUCT_KEY_SIZE),
            DEVICE_SECRET_ADDRESS: padded("0123456789abcdef0123456789abcdef", DEVICE_SECRET_SIZE),
            PRODUCT_SECRET_ADDRESS: padded("", PRODUCT_SECRET_SIZE),
            MQTT_INIT_SIGNAL_ADDRESS: (1).to_bytes(4, "little"),
            PCLIENT_POINTER_ADDRESS: pclient.to_bytes(4, "little"),
            pclient + MQTT_CLIENT_STATE_OFFSET: (2).to_bytes(4, "little"),
        }

    def test_live_confirmed_fields_decode(self):
        adb = FakeAdb(self._live_memory())
        info = read_phnix_modem_info(adb)

        self.assertEqual(info.pid, 1234)
        self.assertEqual(info.software_code, "82400644")
        self.assertEqual(info.firmware_version, "V3.3")
        self.assertEqual(info.hardware_code, "82300314")
        self.assertEqual(info.hardware_version, "0000")

        self.assertEqual(info.modem_model, "SIMCom SIM7600E-H")
        self.assertTrue(info.iccid.startswith("8933"))
        self.assertTrue(info.imsi.startswith("20801"))
        self.assertEqual(info.imei, "860147123456789")
        self.assertEqual(info.sim.card_status, 1)
        self.assertEqual(info.sim.app_state, 7)

        self.assertEqual(info.serving.registration_state, 1)
        self.assertEqual(info.serving.cs_attach_state, 1)
        self.assertEqual(info.serving.ps_attach_state, 1)
        self.assertEqual(info.serving.radio_interface_0, 8)
        self.assertEqual(info.current_plmn_valid, 1)
        self.assertEqual(info.mcc, 262)
        self.assertEqual(info.mnc, 1)
        self.assertEqual(info.network_description, "TDG")
        self.assertEqual(info.roaming_valid, 1)
        self.assertEqual(info.roaming_indicator, 0)
        self.assertEqual(info.lac, 0xFFFE)
        self.assertEqual(info.cell_id, 44867840)

        self.assertTrue(info.rs485_ok)
        self.assertFalse(info.cloud_error)
        self.assertEqual(info.statistics.current_csq, 17)
        self.assertAlmostEqual(info.statistics.average_csq, 15886 / 932)
        self.assertEqual(info.statistics.mainboard_ota_count, 6)
        self.assertEqual(info.statistics.unverified_device_id_candidate, "WF2210250475")

        self.assertEqual(info.cloud.device_name, info.imei)
        self.assertEqual(info.cloud.product_key, "testProductKey")
        self.assertEqual(info.cloud.device_secret, "0123456789abcdef0123456789abcdef")
        self.assertIsNone(info.cloud.product_secret)
        self.assertEqual(info.cloud.mqtt_state, 2)
        self.assertEqual(info.cloud.mqtt_status, "verbunden")

        self.assertEqual(info.network.interface, "rmnet_data0")
        self.assertEqual(info.network.ip_address, "10.236.250.103")
        self.assertEqual(info.network.prefix_length, 28)
        self.assertEqual(info.network.gateway, "10.236.250.104")
        self.assertEqual(info.read_errors, [])

    def test_hex_transport_is_exact_even_with_shell_crlf(self):
        raw = bytes(range(128))
        adb = FakeAdb({STATISTICS_ADDRESS: raw})
        value = read_process_memory(adb, 1234, STATISTICS_ADDRESS, 128)
        self.assertEqual(value, raw)
        self.assertEqual(len(value), 128)

    def test_error_bits_are_readable_but_do_not_send_bus_traffic(self):
        memory = self._live_memory()
        memory[ERROR_STATUS_ADDRESS] = ((1 << 0) | (1 << 5) | (1 << 7)).to_bytes(4, "little")
        adb = FakeAdb(memory)
        info = read_phnix_modem_info(adb)
        self.assertFalse(info.rs485_ok)
        self.assertTrue(info.cloud_error)
        self.assertIn("485-Verbindungsfehler", info.error_messages)
        self.assertIn("Cloud-Verbindungsfehler", info.error_messages)
        self.assertIn("CRC-Fehler", info.error_messages)
        self.assertFalse(any("ttyHSL2" in command for command in adb.commands))

    def test_short_reads_are_field_local_and_do_not_crash_page(self):
        memory = self._live_memory()
        memory[STATISTICS_ADDRESS] = b"short"
        memory[ICCID_ADDRESS] = b""
        adb = FakeAdb(memory)
        info = read_phnix_modem_info(adb)
        self.assertEqual(info.pid, 1234)
        self.assertEqual(info.firmware_version, "V3.3")
        self.assertIsNone(info.iccid)
        self.assertIsNone(info.statistics.current_csq)
        self.assertEqual(info.imei, "860147123456789")
        self.assertEqual(info.cloud.mqtt_state, 2)
        self.assertGreaterEqual(len(info.read_errors), 2)

    def test_missing_process_returns_unavailable_model(self):
        info = read_phnix_modem_info(FakeAdb({}, pid=""))
        self.assertIsNone(info.pid)
        self.assertTrue(info.read_errors)

    def test_statistics_and_duration_helpers(self):
        stats = decode_statistics(self._statistics_block())
        self.assertEqual(stats.strongest_csq, 19)
        self.assertEqual(stats.upload_count, 588940)
        self.assertIn("Tage", format_seconds(35376928))
        self.assertIn("35.376.928 s", format_seconds(35376928))


if __name__ == "__main__":
    unittest.main()
