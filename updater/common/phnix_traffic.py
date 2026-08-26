"""Passive phnixIot4G traffic tracing primitives.

This module deliberately only manages a tracer attached to the already running
service.  It never opens a socket or a serial device and it never sends protocol
data.  The on-device helper is removed again when tracing is disabled.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .adb_transport import AdbClient

SUPPORTED_BUILD_ID = "af4dcae12639bedce833ee5efa5da009777b6319"
MAX_PAYLOAD = 64 * 1024
REMOTE_HELPER = "/data/local/tmp/foxair_traffic_trace"
REMOTE_STATE = "/data/local/tmp/foxair-traffic"


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
        return cls(
            timestamp=str(raw.get("timestamp") or datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")),
            protocol=str(raw.get("protocol", "unknown")),
            direction=str(raw.get("direction", "rx")),
            channel=str(raw.get("channel", "unknown")),
            length=length,
            payload_type=str(raw.get("payload_type", "binary")),
            payload_hex=raw.get("payload_hex"),
            payload_text=text,
            fields=fields,
            sensitive=bool(raw.get("sensitive", False)),
        )


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


def parse_gdb_trace(content: str) -> str:
    """Convert bounded GDB hook records to the canonical JSON-lines format."""
    result = []
    for line in content.splitlines():
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

    def enable(self) -> str:
        self.adb.push(self.helper, REMOTE_HELPER + ".new")
        self.adb.shell(
            f"chmod 700 {REMOTE_HELPER}.new && mv {REMOTE_HELPER}.new {REMOTE_HELPER} && "
            f"{REMOTE_HELPER} start --build-id {SUPPORTED_BUILD_ID}"
        )
        return self.status()

    def disable(self, *, delete_data: bool = True) -> None:
        cleanup = " --purge" if delete_data else ""
        self.adb.shell(f"if [ -x {REMOTE_HELPER} ]; then {REMOTE_HELPER} stop{cleanup}; fi; rm -f {REMOTE_HELPER} {REMOTE_HELPER}.new")

    def status(self) -> str:
        return self.adb.shell(f"if [ -x {REMOTE_HELPER} ]; then {REMOTE_HELPER} status; else echo inactive; fi")

    def events(self) -> str:
        raw = self.adb.shell(f"if [ -r {REMOTE_STATE}/raw.log ]; then cat {REMOTE_STATE}/raw.log; fi")
        return parse_gdb_trace(raw)
