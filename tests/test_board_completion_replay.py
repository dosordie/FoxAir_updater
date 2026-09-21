"""Regression tests for post-transfer C5A8 replays in the VM board peer."""

import unittest

from tools.testvm.work_lab.rs485_fault_emulator import (
    completion_replay_ack,
    crc16_modbus,
)


class CompletionReplayTests(unittest.TestCase):
    def setUp(self):
        self.firmware = bytes((index % 251 for index in range(292986)))
        self.total_blocks = (len(self.firmware) + 167) // 168

    def payload(self, block):
        start = (block - 1) * 168
        value = self.firmware[start:start + 168]
        return value + b"\xff" * (168 - len(value))

    def test_acknowledges_durable_checkpoint_replay_without_advancing_state(self):
        # 0x40000 is the durable checkpoint observed after the live resume
        # completed.  The first full C5A8 block at/after it must remain valid.
        block = (0x40000 // 168) + 1
        ack_b, ack = completion_replay_ack(
            ssid=0x63, total=self.total_blocks, block=block,
            block_size=168, total_blocks=self.total_blocks,
            payload=self.payload(block), firmware=self.firmware,
        )
        self.assertEqual(ack_b, 1)
        self.assertEqual(int.from_bytes(ack[13:15], "big"), block)
        self.assertEqual(ack[-2:], crc16_modbus(ack[:-2]))

    def test_final_replay_uses_terminal_ack_value(self):
        block = self.total_blocks
        ack_b, ack = completion_replay_ack(
            ssid=0x63, total=block, block=block,
            block_size=168, total_blocks=block,
            payload=self.payload(block), firmware=self.firmware,
        )
        self.assertEqual(ack_b, 2)
        self.assertEqual(int.from_bytes(ack[11:13], "big"), 2)

    def test_rejects_changed_replay_payload(self):
        block = (0x40000 // 168) + 1
        damaged = bytearray(self.payload(block))
        damaged[0] ^= 0xFF
        with self.assertRaisesRegex(RuntimeError, "firmware mismatch"):
            completion_replay_ack(
                ssid=0x63, total=self.total_blocks, block=block,
                block_size=168, total_blocks=self.total_blocks,
                payload=bytes(damaged), firmware=self.firmware,
            )


if __name__ == "__main__":
    unittest.main()
