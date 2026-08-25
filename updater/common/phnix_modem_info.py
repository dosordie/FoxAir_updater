"""Read-only diagnostics from the running ``phnixIot4G`` process.

The verified LTE build is a 32-bit ARM EXEC/non-PIE ELF.  The addresses below
therefore refer directly to globals in that exact build.  This module only
reads process memory and normal Linux network state through ADB.  It never
opens the Warmlink UART, never sends Modbus/RS485 traffic and never writes
process memory.

Process-memory bytes are transported as hexadecimal text (``dd | od``).  This
avoids CR/LF or shell framing changes in binary ``adb shell`` output on Windows.
All reads are best-effort and independent: unavailable or malformed values stay
``None`` and are reported as diagnostic hints instead of aborting the page.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Protocol


PHNIX_PROCESS = "phnixIot4G"

# Live-confirmed globals for the verified 747440-byte phnixIot4G build.
STATISTICS_ADDRESS = 0x91B60
STATISTICS_SIZE = 128
ERROR_STATUS_ADDRESS = 0x93124
OTA_DEVICE_INFO_ADDRESS = 0x933AC
BOARD_SOFTWARE_CODE_ADDRESS = 0x935E1
BOARD_SOFTWARE_VERSION_ADDRESS = 0x935EA
BOARD_HARDWARE_CODE_ADDRESS = 0x935EF
BOARD_HARDWARE_VERSION_ADDRESS = 0x935F8
BOARD_INFO_ADDRESS = BOARD_SOFTWARE_CODE_ADDRESS
BOARD_INFO_SIZE = 28

ICCID_ADDRESS = 0x9365C
ICCID_SIZE = 22
IMSI_ADDRESS = 0x93674
IMSI_SIZE = 17
IMEI_ADDRESS = 0x93688
IMEI_SIZE = 32
MQTT_INIT_SIGNAL_ADDRESS = 0x936A8

PCLIENT_POINTER_ADDRESS = 0x94EB4
MQTT_CLIENT_STATE_OFFSET = 0x4DC

ROAMING_VALID_ADDRESS = 0x97FE8
ROAMING_INDICATOR_ADDRESS = 0x97FEC

CURRENT_PLMN_VALID_ADDRESS = 0x98020
MCC_ADDRESS = 0x98022
MNC_ADDRESS = 0x98024
NETWORK_DESCRIPTION_ADDRESS = 0x98026
NETWORK_DESCRIPTION_SIZE = 64

LAC_ADDRESS = 0x98168
CELL_ID_ADDRESS = 0x9816C
SERVING_SYSTEM_ADDRESS = 0x981B4
SERVING_SYSTEM_SIZE = 24

MODE_TYPE_ADDRESS = 0x98912
DEVICE_SECRET_ADDRESS = 0x9896C
DEVICE_SECRET_SIZE = 64
PRODUCT_SECRET_ADDRESS = 0x989B0
PRODUCT_SECRET_SIZE = 64
DEVICE_NAME_ADDRESS = 0x98A58
DEVICE_NAME_SIZE = 64
PRODUCT_KEY_ADDRESS = 0x98A98
PRODUCT_KEY_SIZE = 24
SIM_STATUS_ADDRESS = 0x98AB0
SIM_STATUS_SIZE = 12

MODE_TYPES = {
    1: "SIMCom SIM7600SA-H",
    2: "SIMCom SIM7600E-H",
    3: "anderer/China-Modellpfad",
}

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
class PhnixSimStatus:
    card_status: int | None = None
    app_type: int | None = None
    app_state: int | None = None


@dataclass(slots=True)
class PhnixServingSystem:
    registration_state: int | None = None
    cs_attach_state: int | None = None
    ps_attach_state: int | None = None
    selected_network: int | None = None
    radio_interface_count: int | None = None
    radio_interface_0: int | None = None


@dataclass(slots=True)
class PhnixNetworkInfo:
    interface: str | None = None
    ip_address: str | None = None
    prefix_length: int | None = None
    gateway: str | None = None


@dataclass(slots=True)
class PhnixCloudInfo:
    device_name: str | None = None
    product_key: str | None = None
    device_secret: str | None = None
    product_secret: str | None = None
    pclient_pointer: int | None = None
    mqtt_state: int | None = None
    mqtt_init_signal: int | None = None

    @property
    def mqtt_status(self) -> str | None:
        if self.pclient_pointer is None:
            return None
        if self.pclient_pointer == 0:
            return "nicht initialisiert"
        if self.mqtt_state == 2:
            return "verbunden"
        if self.mqtt_state is None:
            return "Status nicht verfügbar"
        return "nicht verbunden / Verbindungsaufbau"


@dataclass(slots=True)
class PhnixModemInfo:
    pid: int | None = None

    software_code: str | None = None
    firmware_version: str | None = None
    hardware_code: str | None = None
    hardware_version: str | None = None

    modem_type: int | None = None
    iccid: str | None = None
    imsi: str | None = None
    imei: str | None = None
    sim: PhnixSimStatus = field(default_factory=PhnixSimStatus)

    serving: PhnixServingSystem = field(default_factory=PhnixServingSystem)
    current_plmn_valid: int | None = None
    mcc: int | None = None
    mnc: int | None = None
    network_description: str | None = None
    roaming_valid: int | None = None
    roaming_indicator: int | None = None
    lac: int | None = None
    cell_id: int | None = None

    network: PhnixNetworkInfo = field(default_factory=PhnixNetworkInfo)
    cloud: PhnixCloudInfo = field(default_factory=PhnixCloudInfo)

    error_status: int | None = None
    statistics: PhnixStatistics = field(default_factory=PhnixStatistics)
    read_errors: list[str] = field(default_factory=list)

    @property
    def modem_model(self) -> str | None:
        if self.modem_type is None:
            return None
        return MODE_TYPES.get(self.modem_type, f"unbekannt ({self.modem_type})")

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


def decode_uint16_le(data: bytes) -> int:
    if len(data) != 2:
        raise ValueError(f"uint16 benötigt 2 Byte, erhalten: {len(data)}")
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


def read_process_memory(
    client: AdbLike,
    pid: int,
    address: int,
    length: int,
    *,
    attempts: int = 2,
) -> bytes:
    """Read exact bytes through an ASCII-hex shell transport.

    Raw ``adb shell`` binary output can acquire CR/LF bytes on Windows or some
    ADB server implementations.  ``od -An -v -tx1`` is available on the target
    used for live verification and gives an unambiguous textual representation.
    """
    if pid <= 0 or address < 0 or length <= 0:
        raise ValueError("Ungültiger Prozessspeicher-Read")

    command = (
        f"dd if=/proc/{pid}/mem bs=1 skip={address} count={length} 2>/dev/null "
        "| od -An -v -tx1"
    )
    last_size = 0
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            text = client.shell(command)
            tokens = re.findall(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{2}(?![0-9A-Fa-f])", text)
            value = bytes(int(token, 16) for token in tokens)
            last_size = len(value)
            if len(value) == length:
                return value
        except Exception as exc:
            last_error = exc
        if attempt + 1 < max(1, attempts):
            time.sleep(0.05)

    if last_error is not None and last_size == 0:
        raise ModemInfoReadError(
            f"Prozessspeicher-Read bei 0x{address:X} fehlgeschlagen: {last_error}"
        )
    raise ModemInfoReadError(
        f"Kurzer Prozessspeicher-Read bei 0x{address:X}: {last_size}/{length} Byte"
    )


def _u32(block: bytes, offset: int) -> int:
    end = offset + 4
    if end > len(block):
        raise ValueError("Block zu kurz")
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
        # Still only a reverse-engineering candidate.  Do not label it as a
        # device/DTU ID until its semantic role is statically confirmed.
        unverified_device_id_candidate=decode_ascii(block[0x6C:0x7C]),
    )


def _read_bytes(
    client: AdbLike,
    info: PhnixModemInfo,
    label: str,
    address: int,
    length: int,
) -> bytes | None:
    assert info.pid is not None
    try:
        return read_process_memory(client, info.pid, address, length)
    except Exception as exc:
        info.read_errors.append(f"{label}: {exc}")
        return None


def _read_ascii(
    client: AdbLike,
    info: PhnixModemInfo,
    label: str,
    address: int,
    length: int,
) -> str | None:
    raw = _read_bytes(client, info, label, address, length)
    return decode_ascii(raw) if raw is not None else None


def _read_u32(
    client: AdbLike,
    info: PhnixModemInfo,
    label: str,
    address: int,
) -> int | None:
    raw = _read_bytes(client, info, label, address, 4)
    return decode_uint32_le(raw) if raw is not None else None


def _read_u16(
    client: AdbLike,
    info: PhnixModemInfo,
    label: str,
    address: int,
) -> int | None:
    raw = _read_bytes(client, info, label, address, 2)
    return decode_uint16_le(raw) if raw is not None else None


def _read_u8(
    client: AdbLike,
    info: PhnixModemInfo,
    label: str,
    address: int,
) -> int | None:
    raw = _read_bytes(client, info, label, address, 1)
    return raw[0] if raw is not None else None


def _decode_route_gateway(value: str) -> str | None:
    try:
        raw = int(value, 16).to_bytes(4, "little", signed=False)
    except (ValueError, OverflowError):
        return None
    if raw == b"\x00\x00\x00\x00":
        return None
    return ".".join(str(byte) for byte in raw)


def _read_network_info(client: AdbLike, info: PhnixModemInfo) -> None:
    routes = client.shell("cat /proc/net/route", check=False)
    route_candidates: list[tuple[str, str]] = []
    for line in routes.replace("\r", "").splitlines()[1:]:
        fields = line.split()
        if len(fields) < 3:
            continue
        iface, destination, gateway = fields[:3]
        if destination == "00000000" and iface.startswith("rmnet"):
            route_candidates.append((iface, gateway))

    interface = route_candidates[0][0] if route_candidates else None
    address_output = ""
    if interface:
        address_output = client.shell(
            f"ip -o -4 addr show dev {interface} 2>/dev/null", check=False
        )
    if not address_output:
        address_output = client.shell("ip -o -4 addr show 2>/dev/null", check=False)

    selected_ip: tuple[str, str, int] | None = None
    for line in address_output.replace("\r", "").splitlines():
        match = re.search(
            r"^\d+:\s+([^\s:@]+)(?:@[^\s]+)?\s+inet\s+"
            r"(\d+\.\d+\.\d+\.\d+)/(\d+)",
            line.strip(),
        )
        if not match:
            continue
        iface, address, prefix = match.group(1), match.group(2), int(match.group(3))
        if iface.startswith("rmnet") and (interface is None or iface == interface):
            selected_ip = (iface, address, prefix)
            break

    if selected_ip:
        info.network.interface, info.network.ip_address, info.network.prefix_length = selected_ip
    elif interface:
        info.network.interface = interface

    if info.network.interface:
        for iface, gateway_hex in route_candidates:
            if iface == info.network.interface:
                info.network.gateway = _decode_route_gateway(gateway_hex)
                break


def read_phnix_modem_info(client: AdbLike) -> PhnixModemInfo:
    info = PhnixModemInfo()
    try:
        info.pid = _pid(client)
    except Exception as exc:
        info.read_errors.append(str(exc))
        return info

    # Mainboard identity from the C544-populated otaDeviceInfo fields.
    info.software_code = _read_ascii(
        client, info, "Mainboard Softwarecode", BOARD_SOFTWARE_CODE_ADDRESS, 9
    )
    info.firmware_version = _read_ascii(
        client, info, "Mainboard Firmwareversion", BOARD_SOFTWARE_VERSION_ADDRESS, 5
    )
    info.hardware_code = _read_ascii(
        client, info, "Mainboard Hardwarecode", BOARD_HARDWARE_CODE_ADDRESS, 9
    )
    info.hardware_version = _read_ascii(
        client, info, "Mainboard Hardwareversion", BOARD_HARDWARE_VERSION_ADDRESS, 5
    )

    # SIM / modem identity.
    info.iccid = _read_ascii(client, info, "ICCID", ICCID_ADDRESS, ICCID_SIZE)
    info.imsi = _read_ascii(client, info, "IMSI", IMSI_ADDRESS, IMSI_SIZE)
    info.imei = _read_ascii(client, info, "IMEI", IMEI_ADDRESS, IMEI_SIZE)
    info.modem_type = _read_u8(client, info, "ModeType", MODE_TYPE_ADDRESS)

    sim_raw = _read_bytes(client, info, "simStatus", SIM_STATUS_ADDRESS, SIM_STATUS_SIZE)
    if sim_raw is not None:
        try:
            info.sim = PhnixSimStatus(
                card_status=_u32(sim_raw, 0x00),
                app_type=_u32(sim_raw, 0x04),
                app_state=_u32(sim_raw, 0x08),
            )
        except Exception as exc:
            info.read_errors.append("simStatus Dekodierung: " + str(exc))

    # Registration / RAT.
    serving_raw = _read_bytes(
        client, info, "serving_system", SERVING_SYSTEM_ADDRESS, SERVING_SYSTEM_SIZE
    )
    if serving_raw is not None:
        try:
            info.serving = PhnixServingSystem(
                registration_state=_u32(serving_raw, 0x00),
                cs_attach_state=_u32(serving_raw, 0x04),
                ps_attach_state=_u32(serving_raw, 0x08),
                selected_network=_u32(serving_raw, 0x0C),
                radio_interface_count=_u32(serving_raw, 0x10),
                radio_interface_0=_u32(serving_raw, 0x14),
            )
        except Exception as exc:
            info.read_errors.append("serving_system Dekodierung: " + str(exc))

    info.current_plmn_valid = _read_u8(
        client, info, "current_plmn_valid", CURRENT_PLMN_VALID_ADDRESS
    )
    info.mcc = _read_u16(client, info, "MCC", MCC_ADDRESS)
    info.mnc = _read_u16(client, info, "MNC", MNC_ADDRESS)
    info.network_description = _read_ascii(
        client,
        info,
        "Network Description",
        NETWORK_DESCRIPTION_ADDRESS,
        NETWORK_DESCRIPTION_SIZE,
    )
    info.roaming_valid = _read_u32(
        client, info, "roaming_indicator_valid", ROAMING_VALID_ADDRESS
    )
    info.roaming_indicator = _read_u32(
        client, info, "roaming_indicator", ROAMING_INDICATOR_ADDRESS
    )
    info.lac = _read_u16(client, info, "LAC/TAC", LAC_ADDRESS)
    info.cell_id = _read_u32(client, info, "Cell-ID", CELL_ID_ADDRESS)

    # Error bitmap and long-term statistics.
    info.error_status = _read_u32(client, info, "ErrorStatue", ERROR_STATUS_ADDRESS)
    stats_raw = _read_bytes(
        client, info, "Statistik", STATISTICS_ADDRESS, STATISTICS_SIZE
    )
    if stats_raw is not None:
        try:
            info.statistics = decode_statistics(stats_raw)
        except Exception as exc:
            info.read_errors.append("Statistik Dekodierung: " + str(exc))

    # Aliyun identity and MQTT state.  Secrets stay in-memory only; callers must
    # mask them by default and must never add them to normal logs/archives.
    info.cloud.device_name = _read_ascii(
        client, info, "Aliyun DeviceName", DEVICE_NAME_ADDRESS, DEVICE_NAME_SIZE
    )
    info.cloud.product_key = _read_ascii(
        client, info, "Aliyun ProductKey", PRODUCT_KEY_ADDRESS, PRODUCT_KEY_SIZE
    )
    info.cloud.device_secret = _read_ascii(
        client, info, "Aliyun DeviceSecret", DEVICE_SECRET_ADDRESS, DEVICE_SECRET_SIZE
    )
    info.cloud.product_secret = _read_ascii(
        client, info, "Aliyun ProductSecret", PRODUCT_SECRET_ADDRESS, PRODUCT_SECRET_SIZE
    )
    info.cloud.mqtt_init_signal = _read_u32(
        client, info, "MQTT_init_signal", MQTT_INIT_SIGNAL_ADDRESS
    )
    info.cloud.pclient_pointer = _read_u32(
        client, info, "MQTT pclient", PCLIENT_POINTER_ADDRESS
    )
    if info.cloud.pclient_pointer:
        state_address = info.cloud.pclient_pointer + MQTT_CLIENT_STATE_OFFSET
        info.cloud.mqtt_state = _read_u32(
            client, info, "MQTT client_state", state_address
        )

    # Normal Linux network data; explicitly the PDP/mobile interface, not a
    # public Internet IP.  Failure here leaves only network fields unavailable.
    try:
        _read_network_info(client, info)
    except Exception as exc:
        info.read_errors.append("Mobilfunk-Netzwerk: " + str(exc))

    return info
