"""Streaming PHNIX/Warmlink frame decoder and fail-closed OTA observer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FrameError(ValueError):
    pass


class ProtocolViolation(RuntimeError):
    pass


class Direction(str, Enum):
    UNKNOWN = "unknown"
    DTU_TO_BOARD = "dtu-to-board"
    BOARD_TO_DTU = "board-to-dtu"


REGISTER_NAMES = {
    0x0004: "DEVICE_INFO_TRIGGER",
    0x0006: "UART_STATUS_HANDSHAKE",
    0x00C8: "PHNIX_PRODUCT_KEY",
    0x01F4: "DTU_INFO_STATUS",
    0x03E9: "WARMLINK_INFO_1",
    0x0443: "WARMLINK_INFO_2",
    0x049D: "WARMLINK_INFO_3",
    0x04F7: "WARMLINK_INFO_4",
    0x0551: "WARMLINK_INFO_5",
    0x05AB: "WARMLINK_INFO_6",
    0x07D1: "DEVICE_ID_INFO",
    0x082B: "WARMLINK_INFO_8",
    0xC350: "OTA_OFFER",
    0xC357: "OTA_FILE_INFO",
    0xC36A: "OTA_CANCEL_REQUEST",
    0xC36C: "OTA_CANCEL_RESPONSE",
    0xC36E: "OTA_BOARD_STATUS",
    0xC371: "OTA_BLOCK_ACK",
    0xC375: "OTA_ROLLBACK_REQUEST",
    0xC378: "OTA_ROLLBACK_RESPONSE",
    0xC37B: "OTA_STATUS_ACK",
    0xC544: "BOARD_VERSION_INFO",
    0xC5A8: "OTA_FIRMWARE_BLOCK",
}

EXPECTED_DIRECTIONS = {
    0x00C8: Direction.BOARD_TO_DTU,
    0xC350: Direction.DTU_TO_BOARD,
    0xC357: Direction.DTU_TO_BOARD,
    0xC36A: Direction.DTU_TO_BOARD,
    0xC36C: Direction.BOARD_TO_DTU,
    0xC36E: Direction.BOARD_TO_DTU,
    0xC371: Direction.BOARD_TO_DTU,
    0xC375: Direction.DTU_TO_BOARD,
    0xC378: Direction.BOARD_TO_DTU,
    0xC37B: Direction.DTU_TO_BOARD,
    0xC544: Direction.BOARD_TO_DTU,
    0xC5A8: Direction.DTU_TO_BOARD,
}


def modbus_crc16(data: bytes) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def crc_ok(frame: bytes) -> bool:
    return len(frame) >= 4 and int.from_bytes(frame[-2:], "little") == modbus_crc16(frame[:-2])


@dataclass(frozen=True)
class PhnixFrame:
    raw: bytes
    function: int
    address: int | None
    quantity: int | None
    payload: bytes
    frame_type: str
    direction: Direction = Direction.UNKNOWN

    @property
    def name(self) -> str:
        return REGISTER_NAMES.get(self.address, "UNKNOWN_REGISTER")

    @property
    def expected_direction(self) -> Direction:
        return EXPECTED_DIRECTIONS.get(self.address, Direction.UNKNOWN)

    def decoded(self) -> dict[str, object]:
        result: dict[str, object] = {
            "slave": self.raw[0], "function": self.function,
            "address": self.address, "address_hex": None if self.address is None else f"0x{self.address:04X}",
            "name": self.name, "quantity": self.quantity,
            "frame_type": self.frame_type, "direction": self.direction.value,
            "crc_ok": True,
        }
        data = self.payload
        if self.address == 0x00C8 and len(data) == 32:
            text = data.split(b"\0", 1)[0].decode("ascii", errors="replace")
            result.update(product_key_masked=(text[:4] + "…" + text[-3:]) if len(text) > 8 else "***",
                          product_key_bytes=32)
        elif self.address == 0xC350 and len(data) >= 14:
            result.update(ssid=int.from_bytes(data[0:2], "big"),
                          software_code=data[2:10].decode("ascii", errors="replace"),
                          software_version=data[10:14].decode("ascii", errors="replace"))
        elif self.address == 0xC357 and len(data) >= 38:
            result.update(ssid=int.from_bytes(data[0:2], "big"),
                          file_size=int.from_bytes(data[2:6], "big"),
                          md5=data[6:38].decode("ascii", errors="replace").upper())
        elif self.address in {0xC36A, 0xC36C, 0xC36E, 0xC375, 0xC378, 0xC37B} and len(data) >= 4:
            result.update(ssid=int.from_bytes(data[0:2], "big"), status=int.from_bytes(data[2:4], "big"))
        elif self.address == 0xC371 and len(data) >= 8:
            result.update(ssid=int.from_bytes(data[0:2], "big"),
                          ack_a=int.from_bytes(data[2:4], "big"),
                          ack_b=int.from_bytes(data[4:6], "big"),
                          block=int.from_bytes(data[6:8], "big"))
        elif self.address == 0xC5A8 and len(data) >= 6:
            result.update(ssid=int.from_bytes(data[0:2], "big"),
                          total_blocks=int.from_bytes(data[2:4], "big"),
                          block=int.from_bytes(data[4:6], "big"),
                          firmware_bytes=len(data) - 6)
        elif self.address == 0xC544 and len(data) >= 26:
            result.update(
                ssid=int.from_bytes(data[0:2], "big"),
                hardware_code=data[2:10].decode("ascii", errors="replace"),
                hardware_version=data[10:14].decode("ascii", errors="replace"),
                software_code=data[14:22].decode("ascii", errors="replace"),
                software_version=data[22:26].decode("ascii", errors="replace"),
            )
        return result


class PhnixStreamParser:
    """Incrementally extract CRC-valid FC03 and PHNIX FC10 frames."""

    def __init__(self, *, direction: Direction = Direction.UNKNOWN, max_buffer: int = 8192):
        self.direction = direction
        self.max_buffer = max_buffer
        self.buffer = bytearray()
        self.discarded = bytearray()

    def feed(self, data: bytes) -> list[PhnixFrame]:
        self.buffer.extend(data)
        frames: list[PhnixFrame] = []
        while self.buffer:
            if self.buffer[0] != 0x63:
                self.discarded.append(self.buffer.pop(0))
                continue
            frame = self._candidate()
            if frame is None:
                break
            if frame is False:
                self.discarded.append(self.buffer.pop(0))
                continue
            frames.append(frame)
            del self.buffer[:len(frame.raw)]
        if len(self.buffer) > self.max_buffer:
            raise FrameError(f"receive buffer exceeded {self.max_buffer} bytes")
        return frames

    def _candidate(self) -> PhnixFrame | bool | None:
        if len(self.buffer) < 2:
            return None
        fc = self.buffer[1]
        if fc == 0x03:
            if len(self.buffer) >= 8 and crc_ok(bytes(self.buffer[:8])):
                raw = bytes(self.buffer[:8])
                return PhnixFrame(raw, fc, int.from_bytes(raw[2:4], "big"),
                                  int.from_bytes(raw[4:6], "big"), b"", "read-request", self.direction)
            if len(self.buffer) < 3:
                return None
            length = 5 + self.buffer[2]
            if len(self.buffer) < length:
                return None
            raw = bytes(self.buffer[:length])
            if not crc_ok(raw):
                return False
            return PhnixFrame(raw, fc, None, None, raw[3:-2], "read-response", self.direction)
        if fc != 0x10:
            return False
        if len(self.buffer) < 7:
            return None
        # A normal FC10 acknowledgement is exactly eight bytes. Check it
        # before treating byte 6 as a data-frame byte count.
        if len(self.buffer) >= 8 and crc_ok(bytes(self.buffer[:8])):
            raw = bytes(self.buffer[:8])
            return PhnixFrame(raw, fc, int.from_bytes(raw[2:4], "big"),
                              int.from_bytes(raw[4:6], "big"), b"", "write-ack", self.direction)
        length = 9 + self.buffer[6]
        if len(self.buffer) < length:
            return None
        raw = bytes(self.buffer[:length])
        if not crc_ok(raw):
            return False
        return PhnixFrame(raw, fc, int.from_bytes(raw[2:4], "big"),
                          int.from_bytes(raw[4:6], "big"), raw[7:-2], "data", self.direction)


@dataclass
class OtaRunTracker:
    state: str = "idle"
    ssid: int | None = None
    file_size: int | None = None
    md5: str | None = None
    total_blocks: int | None = None
    last_sent_block: int = 0
    last_acked_block: int = 0
    retries: int = 0
    cancelled: bool = False
    history: list[str] = field(default_factory=list)

    def observe(self, frame: PhnixFrame) -> str:
        item = frame.decoded()
        if frame.direction != Direction.UNKNOWN and frame.expected_direction != Direction.UNKNOWN:
            if frame.direction != frame.expected_direction:
                raise ProtocolViolation(f"{frame.name} in unexpected direction {frame.direction.value}")
        ssid = item.get("ssid")
        if ssid is not None:
            if self.ssid is None:
                self.ssid = int(ssid)
            elif self.ssid != ssid:
                raise ProtocolViolation("SSID changed during OTA run")
        address = frame.address
        event = frame.name
        if address == 0xC350:
            if self.state not in {"idle", "offer_seen"}:
                raise ProtocolViolation(f"C350 not allowed in {self.state}")
            self.state = "offer_seen"
        elif address == 0xC357:
            if self.state not in {"offer_accepted", "metadata_seen"}:
                raise ProtocolViolation("C357 before C36E status 1")
            size, md5 = int(item["file_size"]), str(item["md5"])
            if self.file_size is not None and (size, md5) != (self.file_size, self.md5):
                raise ProtocolViolation("C357 metadata changed during OTA run")
            self.file_size, self.md5, self.state = size, md5, "metadata_seen"
        elif address == 0xC36E:
            status = item.get("status")
            if status == 1 and self.state == "offer_seen":
                self.state = "offer_accepted"
            elif status == 2 and self.state == "metadata_seen":
                self.state = "metadata_accepted"
            elif status in {3, 4, 5, 6, 7}:
                self.state = f"board_status_{status}"
            else:
                raise ProtocolViolation(f"unexpected C36E status {status} in {self.state}")
        elif address == 0xC5A8:
            if self.state not in {"metadata_accepted", "data_active"}:
                raise ProtocolViolation("C5A8 before metadata acceptance")
            block = int(item["block"])
            if self.cancelled:
                raise ProtocolViolation("C5A8 after confirmed cancel")
            if block == self.last_sent_block:
                self.retries += 1
            elif block != self.last_sent_block + 1:
                raise ProtocolViolation("C5A8 block sequence jumped or moved backwards")
            self.last_sent_block = block
            self.total_blocks = int(item["total_blocks"])
            self.state = "data_active"
        elif address == 0xC371:
            block, ack_a, ack_b = int(item["block"]), int(item["ack_a"]), int(item["ack_b"])
            if ack_a != 1 or block != self.last_sent_block or ack_b not in {1, 2}:
                raise ProtocolViolation("invalid C371 acknowledgement")
            if ack_b == 2 and block != self.total_blocks:
                raise ProtocolViolation("final C371 before final block")
            self.last_acked_block = block
            self.state = "last_block_acked" if ack_b == 2 else "data_active"
        elif address == 0xC36A:
            self.state = "cancel_pending"
        elif address == 0xC36C:
            if self.state != "cancel_pending" or item.get("status") != 1:
                raise ProtocolViolation("invalid or unsolicited C36C")
            self.cancelled, self.state = True, "cancelled"
        self.history.append(event)
        return self.state
