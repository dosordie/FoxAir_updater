import unittest

from updater.common.phnix_frames import (
    Direction, OtaRunTracker, PhnixStreamParser, ProtocolViolation, modbus_crc16,
)


def fc10(address: int, quantity: int, payload: bytes) -> bytes:
    raw = bytes([0x63, 0x10]) + address.to_bytes(2, "big") + quantity.to_bytes(2, "big") + bytes([len(payload)]) + payload
    return raw + modbus_crc16(raw).to_bytes(2, "little")


class FrameParserTests(unittest.TestCase):
    def test_product_key_200_to_215_is_one_masked_32_byte_identity(self):
        payload = b"a5cVutQfC8x".ljust(32, b"\0")
        frame = PhnixStreamParser(direction=Direction.BOARD_TO_DTU).feed(fc10(0x00C8, 16, payload))[0]
        decoded = frame.decoded()
        self.assertEqual(frame.name, "PHNIX_PRODUCT_KEY")
        self.assertEqual(decoded["product_key_bytes"], 32)
        self.assertNotIn("a5cVutQfC8x", str(decoded))

    def test_fragmented_and_concatenated_frames(self):
        first = fc10(0xC36A, 2, b"\x00\x63\x00\x01")
        second = fc10(0xC36C, 2, b"\x00\x63\x00\x01")
        parser = PhnixStreamParser()
        self.assertEqual(parser.feed(first[:5]), [])
        frames = parser.feed(first[5:] + second)
        self.assertEqual([frame.address for frame in frames], [0xC36A, 0xC36C])

    def test_c5a8_phnix_quantity_bytecount_exception(self):
        payload = b"\x00\x63\x00\x01\x00\x01" + bytes(range(168))
        frame = PhnixStreamParser().feed(fc10(0xC5A8, 0x57, payload))[0]
        self.assertEqual(frame.quantity, 0x57)
        self.assertEqual(frame.decoded()["firmware_bytes"], 168)

    def test_resynchronizes_after_noise(self):
        packet = fc10(0xC36C, 2, b"\x00\x63\x00\x01")
        parser = PhnixStreamParser()
        frames = parser.feed(b"\x00\xffgarbage" + packet)
        self.assertEqual(frames[0].address, 0xC36C)
        self.assertGreater(len(parser.discarded), 0)

    def test_real_c544_and_status_7_ack(self):
        c544 = bytes.fromhex(
            "63 10 C5 44 00 0D 1A 00 63 38 32 33 30 30 33 31 34 "
            "30 30 30 30 38 32 34 30 30 36 34 34 30 30 33 33 CC F0"
        )
        c37b = bytes.fromhex("63 10 C3 7B 00 02 04 00 63 00 07 B5 A8")
        first = PhnixStreamParser(direction=Direction.BOARD_TO_DTU).feed(c544)[0].decoded()
        second = PhnixStreamParser(direction=Direction.DTU_TO_BOARD).feed(c37b)[0].decoded()
        self.assertEqual(first["software_code"], "82400644")
        self.assertEqual(first["software_version"], "0033")
        self.assertEqual(second["status"], 7)


class OtaRunTrackerTests(unittest.TestCase):
    def parse(self, address, quantity, payload, direction):
        return PhnixStreamParser(direction=direction).feed(fc10(address, quantity, payload))[0]

    def test_pre_c5a8_handshake_then_cancel(self):
        tracker = OtaRunTracker()
        offer = b"\x00\x63" + b"82400644" + b"0033"
        metadata = b"\x00\x63" + (287598).to_bytes(4, "big") + b"ceb6a4bf386ff644e23e410023e74673"
        sequence = [
            self.parse(0xC350, 7, offer, Direction.DTU_TO_BOARD),
            self.parse(0xC36E, 2, b"\x00\x63\x00\x01", Direction.BOARD_TO_DTU),
            self.parse(0xC357, 19, metadata, Direction.DTU_TO_BOARD),
            self.parse(0xC36E, 2, b"\x00\x63\x00\x02", Direction.BOARD_TO_DTU),
            self.parse(0xC36A, 2, b"\x00\x63\x00\x01", Direction.DTU_TO_BOARD),
            self.parse(0xC36C, 2, b"\x00\x63\x00\x01", Direction.BOARD_TO_DTU),
        ]
        for frame in sequence:
            tracker.observe(frame)
        self.assertEqual(tracker.state, "cancelled")
        self.assertTrue(tracker.cancelled)
        self.assertEqual(tracker.last_sent_block, 0)

    def test_blocks_c5a8_before_status_two(self):
        tracker = OtaRunTracker()
        data = b"\x00\x63\x00\x01\x00\x01" + bytes(168)
        with self.assertRaises(ProtocolViolation):
            tracker.observe(self.parse(0xC5A8, 0x57, data, Direction.DTU_TO_BOARD))

    def test_rejects_wrong_direction(self):
        tracker = OtaRunTracker()
        with self.assertRaises(ProtocolViolation):
            tracker.observe(self.parse(0xC36A, 2, b"\x00\x63\x00\x01", Direction.BOARD_TO_DTU))

    def test_complete_single_block_transport(self):
        tracker = OtaRunTracker()
        offer = b"\x00\x63" + b"82400644" + b"0033"
        metadata = b"\x00\x63" + (4).to_bytes(4, "big") + b"0" * 32
        block = b"\x00\x63\x00\x01\x00\x01" + b"DATA"
        ack = b"\x00\x63\x00\x01\x00\x02\x00\x01"
        for frame in (
            self.parse(0xC350, 7, offer, Direction.DTU_TO_BOARD),
            self.parse(0xC36E, 2, b"\x00\x63\x00\x01", Direction.BOARD_TO_DTU),
            self.parse(0xC357, 19, metadata, Direction.DTU_TO_BOARD),
            self.parse(0xC36E, 2, b"\x00\x63\x00\x02", Direction.BOARD_TO_DTU),
            self.parse(0xC5A8, 5, block, Direction.DTU_TO_BOARD),
            self.parse(0xC371, 4, ack, Direction.BOARD_TO_DTU),
        ):
            tracker.observe(frame)
        self.assertEqual(tracker.state, "last_block_acked")
        self.assertEqual(tracker.last_acked_block, 1)


if __name__ == "__main__":
    unittest.main()
