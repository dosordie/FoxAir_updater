"""Read-only PHNIX ttyGS0 debug capture and diagnostic parsing.

This module deliberately has no dependency on the OTA controller.  Its events are
diagnostic facts only; callers must never use them to advance a safety state.
"""

from __future__ import annotations

import re
import socket
import threading
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol


PHNIX_USB_ID = r"USB\VID_1E0E&PID_9001&MI_04"

TRANSLATIONS = {
    "modbus校验失败": "Modbus-CRC-Prüfung des empfangenen Mainboard-Telegramms fehlgeschlagen.",
    "收到主板回复的pk，pk已存储，不做任何操作": "ProductKey-Antwort vom Mainboard empfangen; ProductKey bereits gespeichert; keine weitere Aktion.",
    "收到主板回复的pk，检查是否已经存储pk": "ProductKey-Antwort vom Mainboard empfangen; gespeicherten ProductKey prüfen.",
    "================>主板升级指令": "Mainboard-OTA-/Update-Verarbeitung.",
    "DTU 发送给主板的固件包信息:": "DTU überträgt Firmwarepaketdaten an das Mainboard.",
    "升级包传输完成": "Firmwarepaket-Übertragung an das Mainboard abgeschlossen.",
    "推送数据成功<3>": "OTA-Status-/Fortschrittsmeldung erfolgreich übertragen.",
    "主板升级成功<5>": "Mainboard meldet Firmwareupdate erfolgreich.",
    "主板升级结束": "Mainboard-OTA-Ablauf beendet.",
    "FINISH推送完成，无需断电续传": "Übertragung/Verarbeitung abgeschlossen; kein OTA-Resume nach Stromunterbrechung erforderlich.",
    "推送dtu软硬件代码版本号到芬尼云": "DTU Software-/Hardwareversion an PHNIX-Cloud melden.",
    "IOT_MQTT_CheckStateNormal = 1": "Aliyun/MQTT-Verbindung wird vom Originaldienst als normal erkannt.",
    "publish success, packet-id=": "MQTT Publish erfolgreich.",
    "重新获取sim卡iccid": "SIM-ICCID wird erneut abgefragt.",
    "获取sim卡iccid失败": "SIM-ICCID konnte nicht gelesen werden.",
    "重新获取sim卡imsi": "SIM-IMSI wird erneut abgefragt.",
    "获取sim卡imsi失败": "SIM-IMSI konnte nicht gelesen werden.",
    "上报服务器此轮升级失败": "PHNIX-Originaldienst meldet diese OTA-Runde dem Server als fehlgeschlagen/nicht durchgeführt.",
    "主板收到服务器新固件信息，回复允许升级": "Mainboard hat neue Firmwareinformationen erhalten und erlaubt das Update.",
    "主板允许升级": "Mainboard erlaubt das Firmwareupdate.",
    "board固件MD5校验正确！": "MD5-Prüfung der Mainboard-Firmware erfolgreich.",
    "获取IMEI": "IMEI wird ermittelt.",
    "重新采集WF": "WF-Information wird erneut abgefragt.",
    "等待获取主板productKey": "Warte auf ProductKey vom Mainboard.",
    "重新采集pk": "ProductKey wird erneut abgefragt.",
    "等待获取主板2deviceSecret": "Warte auf DeviceSecret-/Cloudzuordnung des Mainboards.",
}


@dataclass(frozen=True)
class DebugEvent:
    kind: str
    total: int | None = None
    current: int | None = None
    progress: float | None = None
    code: str | None = None
    bytes_read: int | None = None
    block_size: int | None = None
    manufacturer_success: bool = False
    terminal_success: bool = False  # Always false: controller state remains authoritative.


_TRANSFER = re.compile(r"tal_len:([0-9a-f]+),and:([0-9a-f]+)", re.I)
_BLOCK = re.compile(r"readCount\s*=\s*(\d+)\s+size\s*=\s*(\d+)", re.I)
_CMD_JSON = re.compile(
    r'["\']code["\']\s*:\s*["\'](00(?:43|53))["\'].*?["\']progress["\']\s*:\s*["\']?(\d{1,3})',
    re.I,
)
_CMD_PLAIN = re.compile(r"CMD_OTA.*?code\s*[=: ]+\s*(00(?:43|53)).*?progress\s*[=: ]+\s*(\d{1,3})", re.I)
_DOWNLOAD = re.compile(r"\bdownload\s+(\d{1,3})\s*%", re.I)
_FILE_LENGTH = re.compile(r"下载主板升级文件长度[:：]\s*([0-9A-Fa-fx]+)")
_FILE_OFFSET = re.compile(r"传输主板升级文件偏移[:：]\s*([0-9A-Fa-fx]+)")
_CHINESE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def parse_debug_line(line: str) -> DebugEvent | None:
    """Parse supplementary OTA diagnostics without ever producing terminal success."""
    match = _TRANSFER.search(line)
    if match:
        total, current = (int(value, 16) for value in match.groups())
        if total > 0 and 0 <= current <= total:
            return DebugEvent("transfer-progress", total, current, current * 100.0 / total)
        return None
    match = _DOWNLOAD.search(line)
    if match:
        progress = int(match.group(1))
        if 0 <= progress <= 100:
            return DebugEvent("lte-download-progress", progress=float(progress))
        return None
    match = _BLOCK.search(line)
    if match:
        read, size = map(int, match.groups())
        if 0 <= read <= size and size > 0:
            return DebugEvent("firmware-block", bytes_read=read, block_size=size)
        return None
    match = _CMD_JSON.search(line) or _CMD_PLAIN.search(line)
    if match:
        code, value = match.groups()
        progress = int(value)
        if 0 <= progress <= 100:
            return DebugEvent("cloud-progress", progress=float(progress), code=code)
        return None
    if "主板升级成功<5>" in line:
        return DebugEvent("manufacturer-success", manufacturer_success=True)
    if "升级包传输完成" in line:
        return DebugEvent("transfer-complete")
    if "主板升级结束" in line:
        return DebugEvent("manufacturer-finished")
    if "IOT_MQTT_CheckStateNormal = 1" in line:
        return DebugEvent("mqtt-normal")
    return None


def translations_for(line: str) -> list[str]:
    """Return every distinct explanation found in one physical trace line."""
    matches: list[tuple[int, str]] = []
    for source, translation in TRANSLATIONS.items():
        if any(source != other and source in other and other in line for other in TRANSLATIONS):
            continue
        start = line.find(source)
        if start >= 0:
            matches.append((start, translation))
    for pattern, label in (
        (_FILE_LENGTH, "Mainboard-Firmwaredatei geladen / Dateilänge bestätigt: {value}."),
        (_FILE_OFFSET, "Mainboard-Firmwareübertragung startet/steht bei Offset {value}."),
    ):
        for match in pattern.finditer(line):
            matches.append((match.start(), label.format(value=match.group(1))))
    result: list[str] = []
    for _, translation in sorted(matches, key=lambda item: item[0]):
        if translation not in result:
            result.append(translation)
    if "publish success, packet-id=" in line:
        translation = TRANSLATIONS["publish success, packet-id="]
        if translation not in result:
            result.append(translation)
    return result


def translation_for(line: str) -> str | None:
    translations = translations_for(line)
    return translations[0] if translations else None


def explain_debug_line(line: str) -> str:
    translations = translations_for(line)
    event = parse_debug_line(line)
    if event and event.kind == "lte-download-progress":
        translations.append(f"LTE-DTU lädt Firmwaredatei: {event.progress:.0f} %.")
    if event and event.kind == "transfer-progress":
        translations.append(
            f"PHNIX-Debug: {event.current} / {event.total} Byte ({event.progress:.1f} %)."
        )
    if event and event.kind == "firmware-block":
        label = "Letzter Firmwareblock" if event.bytes_read != event.block_size else "Firmwareblock"
        translations.append(f"{label}: {event.bytes_read} Byte.")
    if not translations and _CHINESE.search(line):
        translations.append("[Noch keine deutsche Erläuterung vorhanden]")
    return line + "".join(f"\n        -> {item}" for item in dict.fromkeys(translations))


_KEY_VALUE = re.compile(
    r"(?i)(device[_-]?secret|devicesecret|iccid|imsi|imei|devicecode|device_code|productkey|product_key)"
    r"(\s*[=:]\s*|[\"']\s*:\s*[\"'])([^\s,;&\"'{}]+)"
)
_TOPIC = re.compile(r"(?i)(/(?:sys|ext|ota|device)/)([^\s\"']+)")
_PHNIX_TOPIC = re.compile(r"(?<![\w/])/(?!sys/|ext/|ota/|device/)([^/\s\"']+)/([^/\s\"']+)(/user(?:/[^\s\"']*)?)", re.I)


def redact_debug_text(text: str) -> str:
    """Redact credentials and subscriber/device identifiers before fan-out."""
    def replace(match: re.Match[str]) -> str:
        key, separator, value = match.groups()
        replacement = "<REDACTED>" if "secret" in key.lower() else _partial_mask(value)
        return key + separator + replacement

    redacted = _KEY_VALUE.sub(replace, text)
    redacted = _TOPIC.sub(lambda m: m.group(1) + "<REDACTED>", redacted)
    return _PHNIX_TOPIC.sub(r"/<REDACTED>/<REDACTED>\3", redacted)


def _partial_mask(value: str) -> str:
    if len(value) <= 4:
        return "<REDACTED>"
    return value[:2] + "***" + value[-2:]


def resolve_phnix_debug_port(records: Iterable[dict[str, str]] | None = None) -> str | None:
    """Resolve only the exact MI_04 interface; ambiguous matches are rejected."""
    if records is None:
        records = _windows_pnp_records()
    matches = {
        str(record.get("port", "")).upper()
        for record in records
        if PHNIX_USB_ID.lower() in str(record.get("instance_id", "")).lower()
        and re.fullmatch(r"COM\d+", str(record.get("port", "")), re.I)
    }
    return next(iter(matches)) if len(matches) == 1 else None


def _windows_pnp_records() -> list[dict[str, str]]:
    try:
        import winreg
    except ImportError:
        return []
    root_path = r"SYSTEM\CurrentControlSet\Enum\USB\VID_1E0E&PID_9001&MI_04"
    records = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root_path)
        index = 0
        while True:
            try:
                child = winreg.EnumKey(root, index)
            except OSError:
                break
            index += 1
            try:
                params = winreg.OpenKey(root, child + r"\Device Parameters")
                port, _ = winreg.QueryValueEx(params, "PortName")
                records.append({"instance_id": PHNIX_USB_ID + "\\" + child, "port": str(port)})
            except OSError:
                continue
    except OSError:
        pass
    return records


def remote_debug_endpoint(host: str, adb_port: int) -> tuple[str, int]:
    port = int(adb_port) + 1
    if not host.strip() or not 1 <= port <= 65535:
        raise ValueError("Ungültiger Remote-PHNIX-Debug-Endpunkt")
    return host.strip(), port


class ReadSource(Protocol):
    description: str
    def read(self, size: int) -> bytes: ...
    def close(self) -> None: ...


class TcpDebugSource:
    def __init__(self, host: str, port: int, timeout: float = 1.0):
        self.description = f"Remote: {host}:{port}"
        self._socket = socket.create_connection((host, port), timeout=timeout)
        self._socket.settimeout(0.5)

    def read(self, size: int) -> bytes:
        try:
            data = self._socket.recv(size)
        except socket.timeout:
            return b""
        if data == b"":
            raise ConnectionError("TCP-Verbindung beendet")
        return data

    def close(self) -> None:
        self._socket.close()


class PhnixDebugCapture:
    """One physical reader shared by named, independently-lived consumers."""
    def __init__(self, source_factory: Callable[[], ReadSource], identity: str = ""):
        self._factory = source_factory
        self.identity = identity
        self._source: ReadSource | None = None
        self._consumers: dict[str, Callable[[str, DebugEvent | None], None]] = {}
        self._status_consumers: dict[str, Callable[[str, str | None], None]] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._opened = threading.Event()
        self._thread: threading.Thread | None = None
        self.status = "Getrennt"
        self.last_error: str | None = None

    @property
    def active(self) -> bool:
        with self._lock:
            return self._source is not None

    def add_consumer(self, name: str, callback: Callable[[str, DebugEvent | None], None]) -> bool:
        with self._lock:
            self._consumers[name] = callback
            if self._source is not None or (self._thread is not None and self._thread.is_alive()):
                return True
            self._stop.clear()
            self._opened.clear()
            self.status = "Verbinde …"
            self._notify_status()
            self._thread = threading.Thread(target=self._read_loop, daemon=True, name="phnix-debug-reader")
            self._thread.start()
        self._opened.wait(2.0)
        return self.active

    def remove_consumer(self, name: str) -> None:
        with self._lock:
            self._consumers.pop(name, None)
            if not self._consumers:
                self._stop.set()

    def has_consumer(self, name: str) -> bool:
        with self._lock:
            return name in self._consumers

    def add_status_consumer(self, name: str, callback: Callable[[str, str | None], None]) -> None:
        with self._lock:
            self._status_consumers[name] = callback
            status, error = self.status, self.last_error
        callback(status, error)

    def remove_status_consumer(self, name: str) -> None:
        with self._lock:
            self._status_consumers.pop(name, None)

    def _notify_status(self) -> None:
        with self._lock:
            callbacks = list(self._status_consumers.values())
            status, error = self.status, self.last_error
        for callback in callbacks:
            callback(status, error)

    def _read_loop(self) -> None:
        pending = ""
        source = None
        try:
            source = self._factory()
            with self._lock:
                if self._stop.is_set() or not self._consumers:
                    return
                self._source = source
                self.status = "Verbunden"
                self.last_error = None
            self._notify_status()
            self._opened.set()
            while not self._stop.is_set():
                chunk = source.read(8192)
                if not chunk:
                    continue
                pending += chunk.decode("utf-8", errors="replace")
                lines = pending.splitlines(keepends=True)
                pending = "" if not lines or lines[-1].endswith(("\r", "\n")) else lines.pop()
                for raw in lines:
                    original = raw.rstrip("\r\n")
                    safe = redact_debug_text(original)
                    event = parse_debug_line(original)
                    with self._lock:
                        callbacks = list(self._consumers.values())
                    for callback in callbacks:
                        callback(safe, event)
        except Exception as error:
            self.last_error = str(error)
            self.status = "Verbindung beendet" if isinstance(error, ConnectionError) else "Verbindung fehlgeschlagen"
            self._notify_status()
        finally:
            with self._lock:
                if self._source is source:
                    self._source = None
                if self.status == "Verbunden":
                    self.status = "Getrennt"
            self._opened.set()
            if source is not None:
                try:
                    source.close()
                except Exception:
                    pass
            self._notify_status()
