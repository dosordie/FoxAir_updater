import re
import unittest

from updater.common.phnix_modem_info import (
    BOARD_INFO_ADDRESS,
    BOARD_INFO_SIZE,
    ERROR_STATUS_ADDRESS,
    STATISTICS_ADDRESS,
    STATISTICS_SIZE,
    decode_statistics,
    format_seconds,
    read_phnix_modem_info,
)


class FakeAdb:
    def __init__(self, memory: dict[int, bytes], pid: str = "1234"):
        self.memory = memory
        self.pid = pid
        self.commands: list[str] = []

    def shell(self, command: str, check: bool = True) -> str:
        self.commands.append(command)
        if command == "pidof phnixIot4G":
            return self.pid
        raise AssertionError(command)

    def run(self, *args: str, binary: bool = False, check: bool = True):
        self.assert_binary(binary)
        self.assert_read_only(args)
        command = args[1]
        self.commands.append(command)
        match = re.search(r"skip=(\d+) count=(\d+)", command)
        if not match:
            raise AssertionError(command)
        address = int(match.group(1))
        length = int(match.group(2))
        return self.memory.get(address, b"")[:length]

    @staticmethod
    def assert_binary(binary: bool):
        if not binary:
            raise AssertionError("process-memory reads must be binary")

    @staticmethod
    def assert_read_only(args: tuple[str, ...]):
        if args[0] != "shell":
            raise AssertionError(args)
        command = args[1]
        if "dd if=/proc/" not in command:
            raise AssertionError(command)
        forbidden = ("of=", "/dev/ttyHSL2", "modbus", "FC03")
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

    def test_live_confirmed_fields_decode(self):
        board = b"82400644\x00V3.3\x0082300314\x000000\x00"
        self.assertEqual(len(board), BOARD_INFO_SIZE)
        memory = {
            BOARD_INFO_ADDRESS: board,
            ERROR_STATUS_ADDRESS: (0).to_bytes(4, "little"),
            STATISTICS_ADDRESS: self._statistics_block(),
        }
        adb = FakeAdb(memory)
        info = read_phnix_modem_info(adb)

        self.assertEqual(info.pid, 1234)
        self.assertEqual(info.software_code, "82400644")
        self.assertEqual(info.firmware_version, "V3.3")
        self.assertEqual(info.hardware_code, "82300314")
        self.assertEqual(info.hardware_version, "0000")
        self.assertTrue(info.rs485_ok)
        self.assertFalse(info.cloud_error)
        self.assertEqual(info.statistics.current_csq, 17)
        self.assertAlmostEqual(info.statistics.average_csq, 15886 / 932)
        self.assertEqual(info.statistics.mainboard_ota_count, 6)
        self.assertEqual(info.statistics.unverified_device_id_candidate, "WF2210250475")
        self.assertEqual(info.read_errors, [])

    def test_error_bits_are_readable_but_do_not_send_bus_traffic(self):
        board = b"82400644\x00V3.3\x0082300314\x000000\x00"
        error = (1 << 0) | (1 << 5) | (1 << 7)
        adb = FakeAdb(
            {
                BOARD_INFO_ADDRESS: board,
                ERROR_STATUS_ADDRESS: error.to_bytes(4, "little"),
                STATISTICS_ADDRESS: self._statistics_block(),
            }
        )
        info = read_phnix_modem_info(adb)
        self.assertFalse(info.rs485_ok)
        self.assertTrue(info.cloud_error)
        self.assertIn("485-Verbindungsfehler", info.error_messages)
        self.assertIn("Cloud-Verbindungsfehler", info.error_messages)
        self.assertIn("CRC-Fehler", info.error_messages)
        self.assertFalse(any("ttyHSL2" in command for command in adb.commands))

    def test_short_reads_are_reported_without_crashing(self):
        adb = FakeAdb({BOARD_INFO_ADDRESS: b"short", ERROR_STATUS_ADDRESS: b"", STATISTICS_ADDRESS: b""})
        info = read_phnix_modem_info(adb)
        self.assertEqual(info.pid, 1234)
        self.assertIsNone(info.software_code)
        self.assertIsNone(info.error_status)
        self.assertGreaterEqual(len(info.read_errors), 3)

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
