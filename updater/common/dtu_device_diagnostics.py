"""Read-only LTE-DTU identity, clock and network diagnostics.

Never opens an AT port, attaches a debugger, changes the system clock or
starts/stops phnixIot4G. The stored OTA_INFO version is informational only;
update authorization remains pinned to the service binary SHA256.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from updater.dtu_ota.build_profiles import DtuBuildIdentificationError, lookup_build

OTA_INFO_PATH = "/data/phnixIot_device_OTA_INFO"
SERVICE_PATH = "/data/phnixIot4G"
OTA_INFO_LENGTH = 220
VERSION_OFFSET = 28
GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc)
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
VERSION_RE = re.compile(rb"V[0-9]{1,3}\.[0-9]{1,3}(?:\.[0-9]{1,3})?")


def parse_ota_info_version(data: bytes) -> str | None:
    """Parse a PHNIX-persisted version, not an authenticated build identity."""
    if len(data) != OTA_INFO_LENGTH:
        return None
    field = data[VERSION_OFFSET:VERSION_OFFSET + 16]
    match = VERSION_RE.match(field)
    if not match:
        return None
    end = match.end()
    # The version field must end before a control/padding byte, not "V1.0evil".
    if end < len(field) and field[end] not in (0, 0x20, 0xFF):
        return None
    return match.group(0).decode("ascii")


def _safe_shell(adb, command: str) -> str:
    try:
        return str(adb.shell(command, check=False) or "").strip()
    except (OSError, ValueError):
        return ""


def read_dtu_identity(adb) -> dict[str, Any]:
    """Return both independent version sources; unknown hashes never authorize OTA."""
    result: dict[str, Any] = {
        "stored_version": None, "stored_status": "not_available",
        "service_version": None, "service_sha256": None,
        "service_build": None, "supported": False,
        "build_status": "unavailable", "version_match": None,
    }
    try:
        raw = adb.read_file(OTA_INFO_PATH)
    except (OSError, ValueError, RuntimeError):
        result["stored_status"] = "not_available"
    else:
        if len(raw) != OTA_INFO_LENGTH:
            result["stored_status"] = "invalid_length"
        else:
            result["stored_version"] = parse_ota_info_version(raw)
            result["stored_status"] = "ok" if result["stored_version"] else "invalid_version"

    digest = _safe_shell(
        adb, "sha256sum '/data/phnixIot4G' 2>/dev/null | awk '{print $1}'"
    ).lower()
    if SHA256_RE.fullmatch(digest):
        result["service_sha256"] = digest
        try:
            profile = lookup_build(digest)
        except DtuBuildIdentificationError:
            result["build_status"] = "unknown"
        else:
            result.update(
                service_version=profile.software_version,
                service_build=profile.key,
                supported=profile.ota_enabled,
                build_status="supported" if profile.ota_enabled else "blocked",
            )
    else:
        result["build_status"] = "unreadable"

    if result["stored_version"] and result["service_version"]:
        result["version_match"] = result["stored_version"] == result["service_version"]
    return result


def _utc_date(value: str) -> datetime | None:
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=timezone.utc)


def classify_clock(dtu_utc: str | None, uptime: float | None, *, host_now: datetime | None = None) -> dict[str, Any]:
    """Classify plausibility, not the unproven underlying synchronization source."""
    host = host_now or datetime.now(timezone.utc)
    parsed = _utc_date(dtu_utc or "")
    result: dict[str, Any] = {
        "state": "unavailable", "drift_seconds": None,
        "approximate_boot_utc": None, "possible_gps_epoch": False,
    }
    if parsed is None:
        return result
    drift = (parsed - host).total_seconds()
    result["drift_seconds"] = round(drift)
    result["state"] = "plausible" if abs(drift) < 86400 else "unsynchronized"
    if uptime is not None and uptime >= 0:
        from datetime import timedelta
        boot = parsed - timedelta(seconds=uptime)
        result["approximate_boot_utc"] = boot.isoformat()
        result["possible_gps_epoch"] = abs((boot - GPS_EPOCH).total_seconds()) < 60
    return result


def read_time_network(adb) -> dict[str, Any]:
    """Probe only passive Linux state; never concurrently send AT commands."""
    host = datetime.now(timezone.utc)
    dtu_date = _safe_shell(adb, "date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null")
    uptime_text = _safe_shell(adb, "cat /proc/uptime 2>/dev/null")
    try:
        uptime = float(uptime_text.split()[0])
    except (ValueError, IndexError):
        uptime = None
    time_pids = _safe_shell(adb, "pidof time_daemon 2>/dev/null")
    rtc_devices = _safe_shell(
        adb, "for d in /dev/rtc*; do test -e \"$d\" && echo \"$d\"; done"
    )
    rtc_value = _safe_shell(
        adb, "for d in /sys/class/rtc/rtc*; do "
        "test -r \"$d/date\" && test -r \"$d/time\" && "
        "echo \"$(cat \"$d/date\") $(cat \"$d/time\")\"; done"
    )
    registered = _safe_shell(
        adb, "cat /proc/net/route 2>/dev/null | awk 'NR>1 && $1 ~ /^rmnet/ && $2 == \"00000000\" {print $1}'"
    )
    mqtt = _safe_shell(adb, "netstat -nt 2>/dev/null | awk '$4 ~ /:1883$/ || $5 ~ /:1883$/ || $4 ~ /:8883$/ || $5 ~ /:8883$/ {print}'")
    # Netstat is supporting evidence, not proof of PHNIX account association.
    mqtt_established = any("ESTABLISHED" in line for line in mqtt.splitlines())
    clock = classify_clock(dtu_date, uptime, host_now=host)
    return {
        "host_capture_utc": host.isoformat(),
        "dtu_clock_utc": dtu_date if _utc_date(dtu_date) else None,
        "uptime_seconds": uptime,
        "clock": clock,
        "time_daemon_running": bool(time_pids),
        "rtc_devices": rtc_devices.splitlines() if rtc_devices else [],
        "rtc_readout": rtc_value.splitlines() if rtc_value else [],
        "modem_clock": None,
        "nitz_status": None,
        "modem_clock_note": "Nicht abgefragt: keine exklusive, sichere AT-Schnittstelle nachgewiesen.",
        "mobile_route_present": bool(registered),
        "mobile_route_interfaces": registered.splitlines() if registered else [],
        "mqtt_tcp_established": mqtt_established,
        "mqtt_tcp_observed": bool(mqtt),
        "cloud_account_binding": "unknown",
        "cloud_provisioning": "unknown",
        "cloud_api": "not_probed",
        "cloud_activity": "not_probed",
    }


def read_dtu_diagnostics(adb) -> dict[str, Any]:
    return {
        "schema": "foxair-dtu-readonly-diagnostics-v1",
        "identity": read_dtu_identity(adb),
        "time_network": read_time_network(adb),
    }
