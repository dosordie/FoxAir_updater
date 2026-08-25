"""Read-only diagnostics from the running ``phnixIot4G`` process.

The verified LTE build is a 32-bit ARM EXEC/non-PIE ELF.  The addresses below
therefore refer directly to stable globals in that exact build.  This module
only reads ``/proc/<PID>/mem`` through ADB.  It intentionally never opens the
Warmlink UART, never sends Modbus/RS485 traffic and never writes process memory.

All reads are best-effort.  A missing process, denied /proc access, a short read
or malformed data produces unavailable fields plus diagnostic messages instead
of raising into the GUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


PHNIX_PROCESS = "phnixIot4G"

# Live-confirmed globals for the verified 747440-byte phnixIot4G build.
ERROR_STATUS_ADDRESS = 0x93124
STATISTICS_ADDRESS = 0x91B60
STATISTICS_SIZE = 128
OTA_DEVICE_INFO_ADDRESS = 0x933AC
BOARD_INFO_ADDRESS = 0x935E1
BOARD_INFO_SIZE = 28

# otaDeviceInfo field offsets relative to BOARD_INFO_ADDRESS.
SOFTWARE_CODE_SLICE = slice(0, 9)
SOFTWARE_VERSION_SLICE = slice(9, 14)
HARDWARE_CODE_SLICE = slice(14, 23)
HARDWARE_VERSION_SLICE = slice(23, 28)

ERROR_BITS: dict[int, str] = {
    0: "485-Verbindungsfehler",
    1: "Adressfehler",
    3: "No PK",
    4: "Signal-/CSQ-Problem",
    5: "Cloud-Verbindungsfehler",
    6: "WF_double_error",
    7: "CRC-Fehler",
    8: "UART485 Init-/Startproblem",
    10: "weiterer Cloud-/Runtimefehler",
}

RS485_ERROR_BITS = {0, 1, 3, 7, 8}
CLOUD_ERROR_BITS = {5, 10}


class AdbLike(Protocol):
    def shell(self, command: str, check: bool = True) -> str: ...

    def run(self, *args: str, binary: bool = False, check: bool = True): ...


class ModemInfoReadError(RuntimeError):
    pass


@dataclass(slots=True)
class PhnixStatistics:
    strongest_csq: int | None = None
    weakest_csq: int | None = None
    online_time: int | None = None
    device_change_count: int | None = None
    on_off_line_count: int | None = None
    work_time: int | None = None
    upload_count: int | None = None
    download_count: int | None = None
    dtu_ota_count: int | None = None
    mainboard_ota_count: int | None = None
    power_reset_count: int | None = None
    active_reset_count: int | None = None
    api_count: int | None = None
    stored_average_csq: int | None = None
    day_upload_count: int | None = None
    current_work_time: int | None = None
    current_online_time: int | None = None
    current_csq: int | None = None
    csq_sum: int | None = None
    csq_samples: int | None = None
    unverified_device_id_candidate: str | None = None

    @property
    def average_csq(self) -> float | None:
        if self.csq_sum is None or not self.csq_samples:
            return None
        return self.csq_sum / self.csq_samples


@dataclass(slots=True)
class PhnixModemInfo:
    pid: int | None = None
    software_code: str | None = None
    firmware_version: str | None = None
    hardware_code: str | None = None
    hardware_version: str | None = None
    error_status: int | None = None
    statistics: PhnixStatistics = field(default_factory=PhnixStatistics)
    read_errors: list[str] = field(default_factory=list)

    @property
    def error_messages(self) -> list[str]:
        if self.error_status is None:
            return []
        result = [text for bit, text in ERROR_BITS.items() if self.error_status & (1 << bit)]
        unknown = self.unknown_error_bits
        if unknown:
            result.append("Unbekannte Fehlerbits: " + ", ".join(str(bit) for bit in unknown))
        return result

    @property
    def unknown_error_bits(self) -> list[int]:
        if self.error_status is None:
            return []
        known_mask = sum(1 << bit for bit in ERROR_BITS)
        unknown_mask = self.error_status & ~known_mask
        return [bit for bit in range(32) if unknown_mask & (1 << bit)]

    @property
    def rs485_ok(self) -> bool | None:
        if self.error_status is None:
            return None
        return not any(self.error_status & (1 << bit) for bit in RS485_ERROR_BITS)

    @property
    def cloud_error(self) -> bool | None:
        if self.error_status is None:
            return None
        return any(self.error_status & (1 << bit) for bit in CLOUD_ERROR_BITS)


def decode_uint32_le(data: bytes) -> int:
    if len(data) != 4:
        raise ValueError(f"uint32 benötigt 4 Byte, erhalten: {len(data)}")
    return int.from_bytes(data, "little", signed=False)


def decode_ascii(data: bytes) -> str | None:
    raw = data.split(b"\x00", 1)[0].rstrip(b" \xff")
    if not raw:
        return None
    if any(byte < 0x20 or byte > 0x7E for byte in raw):
        return None
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return None


def format_seconds(seconds: int | None) -> str:
    if seconds is None:
        return "nicht verfügbar"
    seconds = max(0, int(seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    human = []
    if days:
        human.append(f"{days} Tage")
    if hours or days:
        human.append(f"{hours} Std")
    if minutes or hours or days:
        human.append(f"{minutes} Min")
    human.append(f"{secs} Sek")
    return f"{seconds:,} s ({' '.join(human)})".replace(",", ".")


def _pid(client: AdbLike) -> int:
    text = client.shell(f"pidof {PHNIX_PROCESS}")
    tokens = text.replace("\r", " ").replace("\n", " ").split()
    for token in tokens:
        if token.isdigit():
            return int(token)
    raise ModemInfoReadError(f"{PHNIX_PROCESS} läuft nicht oder PID ist nicht lesbar")


def read_process_memory(client: AdbLike, pid: int, address: int, length: int) -> bytes:
    if pid <= 0 or address < 0 or length <= 0:
        raise ValueError("Ungültiger Prozessspeicher-Read")
    # Decimal skip avoids relying on shell-specific hexadecimal arithmetic.
    command = (
        f"dd if=/proc/{pid}/mem bs=1 skip={address} count={length} "
        "2>/dev/null"
    )
    data = client.run("shell", command, binary=True)
    if not isinstance(data, (bytes, bytearray)):
        raise ModemInfoReadError("ADB lieferte für Prozessspeicher keine Binärdaten")
    value = bytes(data)
    if len(value) != length:
        raise ModemInfoReadError(
            f"Kurzer Prozessspeicher-Read bei 0x{address:X}: {len(value)}/{length} Byte"
        )
    return value


def _u32(block: bytes, offset: int) -> int:
    end = offset + 4
    if end > len(block):
        raise ValueError("Statistikblock zu kurz")
    return decode_uint32_le(block[offset:end])


def decode_statistics(block: bytes) -> PhnixStatistics:
    if len(block) != STATISTICS_SIZE:
        raise ValueError(f"Statistikblock muss {STATISTICS_SIZE} Byte groß sein")
    return PhnixStatistics(
        strongest_csq=_u32(block, 0x00),
        weakest_csq=_u32(block, 0x04),
        online_time=_u32(block, 0x08),
        device_change_count=_u32(block, 0x0C),
        on_off_line_count=_u32(block, 0x10),
        work_time=_u32(block, 0x14),
        upload_count=_u32(block, 0x18),
        download_count=_u32(block, 0x1C),
        dtu_ota_count=_u32(block, 0x20),
        mainboard_ota_count=_u32(block, 0x24),
        power_reset_count=_u32(block, 0x28),
        active_reset_count=_u32(block, 0x2C),
        api_count=_u32(block, 0x38),
        stored_average_csq=_u32(block, 0x3C),
        day_upload_count=_u32(block, 0x40),
        current_work_time=_u32(block, 0x44),
        current_online_time=_u32(block, 0x48),
        current_csq=_u32(block, 0x4C),
        csq_sum=_u32(block, 0x58),
        csq_samples=_u32(block, 0x5C),
        # Live-observed ASCII candidate.  Keep it explicitly unverified until
        # its semantic role is closed statically; the GUI must not label this
        # as a DTU/device ID yet.
        unverified_device_id_candidate=decode_ascii(block[0x6C:0x7C]),
    )


def read_phnix_modem_info(client: AdbLike) -> PhnixModemInfo:
    info = PhnixModemInfo()
    try:
        info.pid = _pid(client)
    except Exception as exc:
        info.read_errors.append(str(exc))
        return info

    assert info.pid is not None

    try:
        board = read_process_memory(client, info.pid, BOARD_INFO_ADDRESS, BOARD_INFO_SIZE)
        info.software_code = decode_ascii(board[SOFTWARE_CODE_SLICE])
        info.firmware_version = decode_ascii(board[SOFTWARE_VERSION_SLICE])
        info.hardware_code = decode_ascii(board[HARDWARE_CODE_SLICE])
        info.hardware_version = decode_ascii(board[HARDWARE_VERSION_SLICE])
        if not any((info.software_code, info.firmware_version, info.hardware_code, info.hardware_version)):
            info.read_errors.append("Mainboard-Info im otaDeviceInfo ist noch leer oder ungültig")
    except Exception as exc:
        info.read_errors.append("Mainboard-Info: " + str(exc))

    try:
        raw_error = read_process_memory(client, info.pid, ERROR_STATUS_ADDRESS, 4)
        info.error_status = decode_uint32_le(raw_error)
    except Exception as exc:
        info.read_errors.append("ErrorStatue: " + str(exc))

    try:
        block = read_process_memory(client, info.pid, STATISTICS_ADDRESS, STATISTICS_SIZE)
        info.statistics = decode_statistics(block)
    except Exception as exc:
        info.read_errors.append("Statistik: " + str(exc))

    return info
