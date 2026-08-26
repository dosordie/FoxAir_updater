"""Passive phnixIot4G traffic tracing primitives.

This module deliberately only manages a tracer attached to the already running
service.  It never opens a socket or a serial device and it never sends protocol
data.  The on-device helper is removed again when tracing is disabled.
"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .adb_transport import AdbClient
from .phnix_frames import PhnixStreamParser, REGISTER_NAMES
MAX_PAYLOAD = 64 * 1024
REMOTE_HELPER = "/data/local/tmp/foxair_traffic_trace"
REMOTE_STATE = "/data/local/tmp/foxair-traffic"

HOOKS = {
    "mqtt_tx_update": ("MQTT", "MQTT TX / user/update"),
    "mqtt_rx_get": ("MQTT", "MQTT RX / user/get"),
    "mqtt_rx_ota": ("MQTT", "MQTT RX / OTA"),
    "mqtt_tx_ota": ("MQTT", "MQTT TX / OTA"),
    "http_ota_chunk": ("HTTP / OTA", "OTA Download-Chunks"),
    "ota_start_mainboard": ("HTTP / OTA", "Mainboard OTA Start"),
    "ota_start_dtu": ("HTTP / OTA", "DTU OTA Start"),
    "provision_linked_go_query": ("Provisionierung", "Linked-Go Query"),
    "provision_legacy_query": ("Provisionierung", "Legacy Query"),
    "provision_create_by_sign": ("Provisionierung", "CreateDeviceBySign"),
    "provision_aliyun_register": ("Provisionierung", "Aliyun Dynamic Register"),
    "provision_aliyun_register_response": ("Provisionierung", "Aliyun Register Response"),
}
DEFAULT_HOOKS = ("mqtt_tx_update",)
PAYLOAD_MODES = ("metadata_only", "preview", "full")


def mask_secret(value: object) -> str:
    """Return the only representation of secrets allowed in logs/exports."""
    if value is None or str(value) == "":
        return "nicht gesetzt"
    text = str(value)
    if len(text) <= 4:
        return "****"
    return "*" * (len(text) - 4) + text[-4:]


_SECRET_KEYS = {"devicesecret", "device_secret", "productsecret", "product_secret", "sign", "signature"}


def sanitize_fields(value: Any) -> Any:
    """Recursively redact credentials before an event enters the ring buffer."""
    if isinstance(value, dict):
        return {
            key: mask_secret(item) if key.lower() in _SECRET_KEYS else sanitize_fields(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_fields(item) for item in value]
    return value


@dataclass(slots=True)
class TrafficEvent:
    timestamp: str
    protocol: str
    direction: str
    channel: str
    length: int
    payload_type: str = "binary"
    payload_hex: str | None = None
    payload_text: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    sensitive: bool = False

    @property
    def summary(self) -> str:
        if self.payload_type == "phnix":
            return (f"0x{self.fields['slave']:02X} FC{self.fields['function']:02X} "
                    f"Reg {self.fields.get('address_hex', '–')} ×{self.fields.get('quantity', 0)}")
        if self.payload_type == "json":
            command = self.fields.get("command") or self.fields.get("cmd") or self.fields.get("code")
            return f"JSON {command}" if command is not None else "JSON " + str(self.fields)[:64]
        return self.payload_hex[:80] if self.payload_hex else ("Chunk" if self.payload_type == "chunk" else "")

    def details(self) -> str:
        raw = self.payload_hex or "–"
        if self.payload_type == "json":
            decoded = json.dumps(self.fields, ensure_ascii=False, indent=2)
        else:
            decoded = json.dumps(self.fields, ensure_ascii=False, indent=2) if self.fields else "Unbekannte Binärdaten"
        return f"Raw ({self.length} Byte):\n{raw}\n\nDekodiert:\n{decoded}"

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "TrafficEvent":
        length = int(raw.get("length", 0))
        if length < 0 or length > MAX_PAYLOAD:
            raise ValueError("payload length outside safe 0..65536 byte range")
        fields = sanitize_fields(raw.get("fields") or {})
        text = raw.get("payload_text")
        # JSON payloads may contain credentials even when a future hook forgets
        # to flag them. Parse and re-encode them before storing anything.
        if raw.get("payload_type") == "json" and isinstance(text, str):
            try:
                text = json.dumps(sanitize_fields(json.loads(text)), ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                text = None if raw.get("sensitive") else text
        sensitive = bool(raw.get("sensitive", False))
        return cls(
            timestamp=str(raw.get("timestamp") or datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")),
            protocol=str(raw.get("protocol", "unknown")),
            direction=str(raw.get("direction", "rx")),
            channel=str(raw.get("channel", "unknown")),
            length=length,
            payload_type=str(raw.get("payload_type", "binary")),
            payload_hex=None if sensitive else raw.get("payload_hex"),
            payload_text=None if sensitive else text,
            fields=fields,
            sensitive=sensitive,
        )


def decode_payload(payload: bytes) -> tuple[str, str | None, dict[str, Any]]:
    """Decode on the host while always returning the unmodified raw hex."""
    raw_hex = payload.hex(" ").upper() or None
    try:
        text = payload.decode("utf-8")
        value = json.loads(text)
        safe = sanitize_fields(value)
        return "json", json.dumps(safe, ensure_ascii=False, indent=2), safe if isinstance(safe, dict) else {"value": safe}
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    parser = PhnixStreamParser(max_buffer=MAX_PAYLOAD)
    frames = parser.feed(payload)
    if len(frames) == 1 and frames[0].raw == payload:
        decoded = frames[0].decoded()
        if frames[0].payload and frames[0].address is not None:
            decoded["values"] = [
                {"address": address, "address_hex": f"0x{address:04X}",
                 "value": int.from_bytes(frames[0].payload[index * 2:index * 2 + 2], "big")}
                for index, address in enumerate(range(frames[0].address,
                    frames[0].address + len(frames[0].payload) // 2))
            ]
            for item in decoded["values"]:
                if item["address"] in REGISTER_NAMES:
                    item["name"] = REGISTER_NAMES[item["address"]]
        return "phnix", None, decoded
    return "binary", None, {}


class EventRing:
    def __init__(self, limit: int = 500):
        self._events: deque[TrafficEvent] = deque(maxlen=limit)

    def add_json_lines(self, content: str) -> int:
        added = 0
        for line in content.splitlines():
            try:
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    continue
                self._events.append(TrafficEvent.from_mapping(raw))
                added += 1
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
        return added

    def snapshot(self) -> list[TrafficEvent]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()


def parse_gdb_trace(content: str, payload_blob: bytes = b"") -> str:
    """Convert bounded GDB hook records to the canonical JSON-lines format."""
    result = []
    for line in content.splitlines():
        if line.startswith("FOXBIN|"):
            parts = line.split("|")
            if len(parts) != 7:
                continue
            _, protocol, direction, channel, length_text, offset_text, pointer = parts
            try:
                length, offset = int(length_text), int(offset_text)
            except ValueError:
                continue
            if length < 0 or length > MAX_PAYLOAD or offset < 0 or offset + length > len(payload_blob):
                continue
            payload = payload_blob[offset:offset + length]
            payload_type, payload_text, fields = decode_payload(payload)
            result.append(json.dumps({
                "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds"),
                "protocol": protocol, "direction": direction, "channel": channel,
                "length": length, "payload_type": payload_type,
                "payload_hex": payload.hex(" ").upper() or None, "payload_text": payload_text,
                "fields": fields, "sensitive": False, "pointer": pointer,
            }, ensure_ascii=False))
            continue
        if line.startswith("FOX|hook_hit|"):
            parts = line.split("|", 4)
            if len(parts) != 5 or parts[2] not in HOOKS:
                continue
            try:
                length = int(parts[3].removeprefix("len="))
            except ValueError:
                continue
            if length < 0 or length > MAX_PAYLOAD or not parts[4].startswith("ptr="):
                continue
            hook_id = parts[2]
            group = HOOKS[hook_id][0]
            protocol = "mqtt" if group == "MQTT" else "http" if group == "HTTP / OTA" else "https"
            direction = "tx" if "_tx_" in hook_id else "rx"
            result.append(json.dumps({
                "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds"),
                "protocol": protocol, "direction": direction, "channel": hook_id,
                "length": length, "payload_type": "metadata", "payload_hex": None,
                "payload_text": None, "fields": {"pointer": parts[4][4:]},
                "sensitive": group == "Provisionierung",
            }, ensure_ascii=False))
            continue
        if line.startswith("META|"):
            parts = line.split("|", 5)
            now = datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")
            if len(parts) == 5 and parts[1] == "ota_start":
                _, _, download_type, target, url = parts
                result.append(json.dumps({
                    "timestamp": now, "protocol": "https" if url.startswith("https:") else "http",
                    "direction": "rx", "channel": "ota_download_start", "length": 0,
                    "payload_type": "metadata", "fields": {"download_type": download_type,
                    "url": url[:1024], "target": target, "status": "aktiv"}, "sensitive": False,
                }, ensure_ascii=False))
            elif len(parts) == 5 and parts[1] == "provision":
                _, _, channel, transport, length_text = parts
                try:
                    safe_length = min(MAX_PAYLOAD, max(0, int(length_text)))
                except ValueError:
                    continue
                result.append(json.dumps({
                    "timestamp": now, "protocol": transport, "direction": "rx",
                    "channel": channel, "length": safe_length, "payload_type": "metadata",
                    "fields": {"response": "beobachtet; sensible Felder vor Logspeicherung verworfen"},
                    "sensitive": True,
                }, ensure_ascii=False))
            continue
        if not line.startswith("FOX|"):
            continue
        parts = line.split("|", 6)
        if len(parts) != 7:
            continue
        _, protocol, direction, channel, length_text, _pointer, hex_text = parts
        try:
            length = int(length_text)
        except ValueError:
            continue
        octets = hex_text.strip().split()
        expected_octets = 0 if channel == "ota_chunk" else length
        if length > MAX_PAYLOAD or len(octets) != expected_octets or any(
            len(item) != 2 or any(c not in "0123456789abcdefABCDEF" for c in item)
            for item in octets
        ):
            continue
        record = {
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds"),
            "protocol": protocol, "direction": direction, "channel": channel,
            "length": length, "payload_type": "chunk" if channel == "ota_chunk" else "binary",
            "payload_hex": " ".join(item.upper() for item in octets) or None,
            "payload_text": None, "sensitive": False,
        }
        if "queryiotdevice" in channel:
            # Provisioning callbacks can contain device_secret. Never let their
            # raw bytes reach the normal ring, log, clipboard, or support ZIP.
            try:
                decoded = bytes.fromhex("".join(octets)).decode("utf-8").rstrip("\x00")
                fields = sanitize_fields(json.loads(decoded))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                fields = {"response": "empfangen; Inhalt aus Sicherheitsgründen maskiert"}
            record.update(payload_type="json", payload_hex=None, fields=fields, sensitive=True)
        result.append(json.dumps(record, ensure_ascii=False))
    return "\n".join(result)


class TrafficTracer:
    """Install, start, poll and remove the ephemeral on-device tracer."""

    def __init__(self, adb: AdbClient, helper: str | Path):
        self.adb = adb
        self.helper = Path(helper)
        self._offset = 0
        self._partial = ""
        self.startup_diagnostics = ""
        self._guardian = None

    def enable(
        self, hooks: Iterable[str] = DEFAULT_HOOKS, *, mode: str = "full",
        max_seconds: int = 120,
    ) -> str:
        self._offset = 0
        self._partial = ""
        self.startup_diagnostics = ""
        selected = tuple(dict.fromkeys(hooks))
        if not selected:
            raise ValueError("Mindestens ein Traffic-Hook muss ausgewählt sein.")
        unknown = [hook for hook in selected if hook not in HOOKS]
        if unknown:
            raise ValueError("Unbekannte Traffic-Hook-ID: " + ", ".join(unknown))
        if mode not in PAYLOAD_MODES:
            raise ValueError("Unbekannter Payload-Modus.")
        if not 15 <= max_seconds <= 600:
            raise ValueError("Die maximale Laufzeit muss zwischen 15 und 600 Sekunden liegen.")
        helper_bytes = self.helper.read_bytes()
        if b"\r\n" in helper_bytes:
            raise ValueError("traffic-trace helper contains CRLF line endings")
        if helper_bytes.splitlines()[:1] != [b"#!/system/bin/sh"]:
            raise ValueError("traffic-trace helper has an invalid shebang")
        # ADB shell/cat is not binary-transparent on all legacy modems. The
        # helper therefore performs every build and process check on-device.
        self.adb.push(self.helper, REMOTE_HELPER + ".new")
        self.adb.shell(f"chmod 700 {REMOTE_HELPER}.new && mv {REMOTE_HELPER}.new {REMOTE_HELPER}")
        # A failed helper start is deliberately non-fatal here: status and both
        # debugger logs must be collected before any caller can consider cleanup.
        arguments = " ".join(f"--hook {hook}" for hook in selected)
        previous_run = self.adb.shell(f"cat {REMOTE_STATE}/run.id 2>/dev/null || true")
        self._guardian = self.adb.popen_shell(
            f"{REMOTE_HELPER} serve {arguments} --mode {mode} --max-seconds {max_seconds}"
        )
        status = "inactive"
        for _attempt in range(20):
            time.sleep(0.25)
            status = self.status()
            if status.startswith("active") or status.startswith("critical|"):
                break
            if self._guardian.poll() is not None:
                break
        if status.startswith("active|run_id="):
            current_run = status.split("|", 2)[1].split("=", 1)[1]
            if previous_run and current_run == previous_run:
                status = "conflict|existing_run=" + current_run
        if not status.startswith("active"):
            self.startup_diagnostics = self._read_startup_diagnostics()
        return status

    def _read_startup_diagnostics(self) -> str:
        sections = []
        for name in ("helper.log", "gdbserver.log", "gdb.log", "raw.log"):
            remote = f"{REMOTE_STATE}/{name}"
            try:
                content = self.adb.read_file(remote).decode("utf-8", errors="replace")
            except Exception as error:
                content = f"<nicht lesbar: {error}>"
            sections.append(f"--- {remote} ---\n{content.rstrip() or '<leer>'}")
        return "\n".join(sections)

    def disable(self, *, delete_data: bool = True) -> None:
        cleanup = " --purge" if delete_data else ""
        self.adb.shell(f"if [ -x {REMOTE_HELPER} ]; then {REMOTE_HELPER} stop{cleanup}; fi; rm -f {REMOTE_HELPER} {REMOTE_HELPER}.new")
        if self._guardian is not None:
            try:
                self._guardian.wait(timeout=3)
            except Exception:
                self._guardian.terminate()
            self._guardian = None

    def status(self) -> str:
        return self.adb.shell(f"if [ -x {REMOTE_HELPER} ]; then {REMOTE_HELPER} status; else echo inactive; fi")

    def events(self) -> str:
        command = (
            f"if [ -r {REMOTE_STATE}/raw.log ]; then "
            f"n=$(wc -c < {REMOTE_STATE}/raw.log); echo FOXAIR_SIZE:$n; "
            f"if [ $n -gt {self._offset} ]; then dd if={REMOTE_STATE}/raw.log bs=1 "
            f"skip={self._offset} count=$((n-{self._offset})) 2>/dev/null; fi; "
            f"else echo FOXAIR_SIZE:0; fi"
        )
        response = self.adb.run("shell", command)
        first, separator, tail = response.partition("\n")
        if not first.startswith("FOXAIR_SIZE:"):
            return ""
        try:
            size = int(first.split(":", 1)[1])
        except ValueError:
            return ""
        # Log truncation/restart: discard the stale partial record and restart.
        if size < self._offset:
            self._offset = 0
            self._partial = ""
            return ""
        self._offset = size
        combined = self._partial + (tail if separator else "")
        if combined and not combined.endswith("\n"):
            complete, _, self._partial = combined.rpartition("\n")
        else:
            complete, self._partial = combined, ""
        try:
            payload_blob = self.adb.read_file(f"{REMOTE_STATE}/payload.bin")
        except Exception:
            payload_blob = b""
        return parse_gdb_trace(complete, payload_blob)


def export_events(events: Iterable[TrafficEvent]) -> str:
    """Create a redacted JSON export; raw sensitive payloads are never used."""
    rows = []
    for event in events:
        row = {
            "timestamp": event.timestamp, "protocol": event.protocol,
            "direction": event.direction, "channel": event.channel,
            "length": event.length, "payload_type": event.payload_type,
            "payload_hex": None if event.sensitive else event.payload_hex,
            "payload_text": None if event.sensitive else event.payload_text,
            "fields": sanitize_fields(event.fields), "sensitive": event.sensitive,
        }
        rows.append(json.dumps(row, ensure_ascii=False))
    return "\n".join(rows)
