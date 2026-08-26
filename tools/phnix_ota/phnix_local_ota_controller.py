#!/usr/bin/env python3
"""Host-side controller for a local PHNIX mainboard OTA via an LTE modem.

The controller is intentionally fail-closed.  Without --execute it performs
only read-only preflight checks.  Runtime modification is delegated to a
build-specific helper that must be verified separately on the real modem.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

# Keep the laboratory script directly executable before it becomes an
# installed package.  Repository checkout and VM deployment both place the
# shared package at one of these two roots.
for candidate in (Path(__file__).resolve().parents[2], Path.cwd()):
    if (candidate / "updater/common/adb_transport.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from updater.common import AdbClient, TransportError
from updater.common.firmware_manifest import FirmwareManifest, ManifestError


EXPECTED_BUILD_ID = "af4dcae12639bedce833ee5efa5da009777b6319"
EXPECTED_SERVICE_SHA256 = "7C573431F0A67620D473419644A83A4F4DC04B8A91BDE5923C74A63BA1EAEDB7"

REMOTE_SERVICE = "/data/phnixIot4G"
REMOTE_CACHE = "/cache/phnixIot_device_OTA"
REMOTE_INFO = "/data/phnixIot_device_OTA_INFO"
REMOTE_STATISTICS = "/data/phnixIot_device_statisic"
REMOTE_HELPER = "/data/phnix_ota_runtime_hook"
REMOTE_HELPER_STAGE = "/data/.phnix_ota_runtime_hook.new"
REMOTE_STAGE_DIR = "/data/phnix_local_ota"
REMOTE_FIRMWARE = f"{REMOTE_STAGE_DIR}/phnixIot_device_OTA.bin"
REMOTE_COMMAND = f"{REMOTE_STAGE_DIR}/ota-command.json"
REMOTE_STATUS = "/tmp/phnix_ota_status.json"
REMOTE_HTTP_PID = "/tmp/phnix_ota_httpd.pid"
REMOTE_SIM_MARKER = "/data/.phnix_ota_simulator"
REMOTE_HANDSHAKE_TRACE = "/tmp/phnix_handshake_trace.json"
REMOTE_HOOK_STATE = "/tmp/phnix_ota_hook"
REMOTE_RUN_ACTIVE = f"{REMOTE_HOOK_STATE}/run.active"
REMOTE_TRANSFER_STARTED = f"{REMOTE_HOOK_STATE}/transfer-started"
REMOTE_INJECTION_STARTED = f"{REMOTE_HOOK_STATE}/injection-started"
DEFAULT_FIRMWARE_URL = "http://127.0.0.1:8081/phnixIot_device_OTA.bin"

OUTPUT_MODE = "auto"
COLOR_ENABLED = True
_LAST_HUMAN_PHASE: str | None = None
_LAST_HUMAN_PERCENT = -1
_LAST_HUMAN_PROGRESS_AT = 0.0
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
CYAN = "\033[1;36m"
RESET = "\033[0m"


class OtaError(RuntimeError):
    pass


@dataclass
class OtaInfo:
    crc_ok: bool
    stored_crc: int
    calculated_crc: int
    system_version: str
    md5: str
    software_code: str
    software_version: str
    offset: int
    length: int


def crc16_x25(data: bytes) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return (~crc) & 0xFFFF


def c_string(data: bytes) -> str:
    return data.split(b"\0", 1)[0].decode("ascii", errors="replace")


def parse_ota_info(raw: bytes) -> OtaInfo:
    if len(raw) != 220:
        raise OtaError(f"OTA_INFO has {len(raw)} bytes; expected 220")
    stored = int.from_bytes(raw[0:4], "little")
    calculated = crc16_x25(raw[4:220])
    return OtaInfo(
        crc_ok=stored == calculated,
        stored_crc=stored,
        calculated_crc=calculated,
        system_version=c_string(raw[28:34]),
        md5=c_string(raw[165:198]),
        software_code=c_string(raw[198:207]),
        software_version=c_string(raw[207:212]),
        offset=int.from_bytes(raw[212:216], "little"),
        length=int.from_bytes(raw[216:220], "little"),
    )


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def command_payload(firmware_url: str, manifest: FirmwareManifest) -> dict:
    return {
        "cmd": "CMD_OTA",
        "code": "0033",
        "param": {
            "softwareCode": manifest.software_code,
            "softwareVer": manifest.display_version,
            "ssid": manifest.target_ssid,
            "fileMD5": manifest.md5,
            "fileSize": manifest.size,
            "otaFileDownloadAddr": firmware_url,
        },
    }


def cancel_payload() -> dict:
    # ota_code_handle() dispatches solely on the numeric value of top-level
    # "code". The cancel handler reads no param fields.
    return {"cmd": "CMD_OTA", "code": "0073"}


def _human_output() -> bool:
    return OUTPUT_MODE == "human" or (OUTPUT_MODE == "auto" and sys.stdout.isatty())


def _paint(text: str, color: str) -> str:
    return f"{color}{text}{RESET}" if COLOR_ENABLED and sys.stdout.isatty() else text


def _human_event(event: str, fields: dict) -> None:
    """Render reassuring milestones while JSON stays available for machines."""
    global _LAST_HUMAN_PHASE, _LAST_HUMAN_PERCENT, _LAST_HUMAN_PROGRESS_AT
    if event in {"same-version-status", "status"}:
        hook = fields.get("hook", {})
        phase = hook.get("phase") if isinstance(hook, dict) else None
        if not phase:
            return
        if phase != _LAST_HUMAN_PHASE:
            _LAST_HUMAN_PHASE = phase
            labels = {
                "verified": "Sicherheitspruefungen bestanden",
                "attaching": "Originaldienst wird kontrolliert vorbereitet",
                "waiting-for-yield-loop": "Warte auf einen sicheren Sendepunkt",
                "c350-probe-attaching": "Warte auf einen sicheren Sendepunkt",
                "parser-injection": "Updateauftrag wurde gestartet",
                "accepted": "Originaldienst hat den Updateauftrag angenommen",
                "c350-sent": "Firmwareangebot wurde an das Mainboard gesendet",
                "c350": "Mainboard prueft das Firmwareangebot",
                "c357": "Mainboard hat die Transferdaten erhalten",
                "c5a8": "Firmware wird zum Mainboard uebertragen",
                "success-report": "Mainboard meldet erfolgreichen Abschluss",
                "success": "Firmware-Update erfolgreich abgeschlossen",
                "c350-same-version": "Gleiche Firmware erkannt - sichere Beendigung",
                "same-version": "Gleiche Firmware erkannt - keine Uebertragung",
            }
            label = labels.get(phase)
            if label:
                good = phase in {"verified", "accepted", "success", "c350-same-version", "same-version"}
                print(_paint(f"[OK] {label}" if good else f"[..] {label}", GREEN if good else CYAN), flush=True)

        info = fields.get("ota_info", {})
        if phase == "c5a8" and isinstance(info, dict) and info.get("crc_ok") is True:
            offset = info.get("offset")
            length = info.get("length")
            if (isinstance(offset, int) and isinstance(length, int)
                    and length > 0 and 0 <= offset <= length):
                percent = 100 if offset >= length else min(99, max(0, round(offset * 100 / length)))
                now = time.monotonic()
                if (percent >= _LAST_HUMAN_PERCENT + 1 or
                        now - _LAST_HUMAN_PROGRESS_AT >= 5 or percent == 100):
                    _LAST_HUMAN_PERCENT = percent
                    _LAST_HUMAN_PROGRESS_AT = now
                    print(_paint(
                        f"[..] Fortschritt: {percent:3d} % "
                        f"({offset:,} / {length:,} Byte)".replace(",", "."), CYAN
                    ), flush=True)
        return
    messages = {
        "preflight": (GREEN, "[OK] Vorpruefung erfolgreich"),
        "state-backed-up": (GREEN, "[OK] Sicherheitskopie des Ausgangszustands erstellt"),
        "firmware-staged": (GREEN, "[OK] Firmware auf das LTE-Modem kopiert"),
        "helper-local-verified": (GREEN, "[OK] Lokaler Update-Helfer geprueft"),
        "helper-installed": (GREEN, "[OK] Update-Helfer sicher auf das LTE-Modem kopiert"),
        "helper-removed": (GREEN, "[OK] Update-Helfer vom LTE-Modem entfernt"),
        "hook-start": (CYAN, "[..] Update gestartet"),
        "same-version-complete": (GREEN, "[OK] Gleichversionstest erfolgreich beendet - keine Firmware geschrieben"),
        "complete": (GREEN, "[OK] Firmware-Uebertragung und Mainboard-Abschluss erfolgreich"),
        "original-state-released": (GREEN, "[OK] LTE-Modem wieder im Originalzustand"),
        "services-restored": (GREEN, "[OK] Originaldienst, Ueberwachung und Cloud-Verbindung laufen"),
        "hook-stopped": (GREEN, "[OK] Update-Helfer sauber beendet"),
        "dry-run-complete": (GREEN, "[OK] Trockenlauf beendet - nichts wurde veraendert"),
        "warning": (YELLOW, f"[WARNUNG] {fields.get('message', 'Pruefung erforderlich')}"),
        "guarded-hold": (RED, "[FEHLER] Update sicher angehalten - keine weiteren Befehle ausfuehren"),
        "manual-recovery-required": (RED, "[FEHLER] Manueller Wiederherstellungsschritt erforderlich"),
        "error": (RED, f"[FEHLER] {fields.get('message', 'Unbekannter Fehler')}"),
    }
    if event == "complete":
        offset = fields.get("offset")
        length = fields.get("length")
        if (isinstance(offset, int) and isinstance(length, int)
                and length > 0 and offset >= length and _LAST_HUMAN_PERCENT < 100):
            _LAST_HUMAN_PERCENT = 100
            print(_paint(
                f"[..] Fortschritt: 100 % "
                f"({offset:,} / {length:,} Byte)".replace(",", "."), CYAN
            ), flush=True)
    item = messages.get(event)
    if item:
        print(_paint(item[1], item[0]), flush=True)


def print_event(event: str, **fields) -> None:
    record = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, **fields}
    if _human_output():
        _human_event(event, fields)
    else:
        print(json.dumps(record, ensure_ascii=False), flush=True)


def verify_original_runtime(adb: AdbClient) -> dict:
    result = {
        "service_pid": adb.shell("pidof phnixIot4G || true"),
        "service_sha256": adb.shell(
            f"sha256sum {REMOTE_SERVICE} | awk '{{print $1}}'"
        ).upper(),
        "watchdog_pids": adb.shell("ps | awk '$4 == \"{helloworld}\" {print $1}'"),
        "mqtt_connection": adb.shell(
            "netstat -nt 2>/dev/null | awk '$4 ~ /:1883$/ || $5 ~ /:1883$/ {print}'"
        ),
        "runtime_helper_absent": adb.shell(f"test -e {REMOTE_HELPER}; echo $?") != "0",
    }
    result["ok"] = bool(
        result["service_pid"]
        and result["service_sha256"] == EXPECTED_SERVICE_SHA256
        and len(str(result["watchdog_pids"]).splitlines()) >= 2
        and result["mqtt_connection"]
        and result["runtime_helper_absent"]
    )
    return result


def original_runtime_status(adb: AdbClient) -> dict:
    """Read-only proof that the modem is back in its unmodified runtime state."""
    service_pid = ""
    service_path = ""
    service_state = ""
    for attempt in range(3):
        pid_before = adb.shell("pidof phnixIot4G || true")
        path = adb.shell(
            "p=$(pidof phnixIot4G | awk '{print $1}'); "
            "test -n \"$p\" && readlink /proc/$p/exe || true"
        )
        state = adb.shell(
            "p=$(pidof phnixIot4G | awk '{print $1}'); "
            "test -n \"$p\" && awk '/^State:|^TracerPid:/ {print}' /proc/$p/status || true"
        )
        pid_after = adb.shell("pidof phnixIot4G || true")
        if pid_before and pid_before == pid_after and path and state:
            service_pid, service_path, service_state = pid_after, path, state
            break
        if attempt < 2:
            time.sleep(0.25)
    service_hash = adb.shell(f"sha256sum {REMOTE_SERVICE} | awk '{{print $1}}'").upper()
    watchdogs = adb.shell("ps | awk '$4 == \"{helloworld}\" {print $1}'")
    http_pid_active = adb.shell(f"test -f {REMOTE_HTTP_PID}; echo $?") == "0"
    http_listener = adb.shell(
        "netstat -lnt 2>/dev/null | awk '$4 ~ /:8081$/ {print}'"
    )
    local_artifacts = adb.shell(f"ls -A {REMOTE_STAGE_DIR} 2>/dev/null || true")
    result = {
        "adb_state": adb.run("get-state").strip(),
        "service_pid": service_pid,
        "service_path": service_path,
        "service_sha256": service_hash,
        "service_state": service_state,
        "debugger_pids": adb.shell("pidof gdbserver gdb || true"),
        "run_active": adb.shell(f"test -f {REMOTE_RUN_ACTIVE}; echo $?") == "0",
        "transfer_started": adb.shell(f"test -f {REMOTE_TRANSFER_STARTED}; echo $?") == "0",
        "injection_started": adb.shell(f"test -f {REMOTE_INJECTION_STARTED}; echo $?") == "0",
        "cloud_guards": adb.shell(
            "iptables -S OUTPUT 2>/dev/null | grep -- '--dport 1883' || true; "
            "iptables -S INPUT 2>/dev/null | grep -- '--sport 1883' || true"
        ),
        "mqtt_connection": adb.shell(
            "netstat -nt 2>/dev/null | awk '$4 ~ /:1883$/ || $5 ~ /:1883$/ {print}'"
        ),
        "watchdog_pids": watchdogs,
        "http_active": http_pid_active or bool(http_listener),
        "http_listener": http_listener,
        "local_ota_artifacts": local_artifacts,
        "runtime_helper_present": adb.shell(f"test -e {REMOTE_HELPER}; echo $?") == "0",
        "ota_info": asdict(parse_ota_info(adb.read_file(REMOTE_INFO))),
        "ota_info_sha256": adb.shell(f"sha256sum {REMOTE_INFO} | awk '{{print $1}}'"),
        "statistics_sha256": adb.shell(f"sha256sum {REMOTE_STATISTICS} | awk '{{print $1}}'"),
    }
    checks = {
        "service_running": bool(service_pid),
        "service_original": service_path == REMOTE_SERVICE and service_hash == EXPECTED_SERVICE_SHA256,
        "service_untraced": "TracerPid:\t0" in service_state or "TracerPid: 0" in service_state,
        "service_not_stopped": "T (stopped)" not in service_state,
        "no_debugger": not result["debugger_pids"],
        "no_local_ota": (
            not result["run_active"]
            and not result["injection_started"]
            and not result["transfer_started"]
        ),
        "no_cloud_guard": not result["cloud_guards"],
        "cloud_connected": "ESTABLISHED" in result["mqtt_connection"],
        "watchdogs_running": len(watchdogs.splitlines()) >= 2,
        "http_stopped": not result["http_active"],
        "staging_clean": not result["local_ota_artifacts"],
        "helper_absent": not result["runtime_helper_present"],
        "ota_info_valid": result["ota_info"]["crc_ok"],
    }
    result["checks"] = checks
    result["original_ok"] = all(checks.values())
    return result


def show_original_status(result: dict) -> None:
    if not _human_output():
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    labels = {
        "service_running": "Originaldienst laeuft",
        "service_original": "Originale Programmdatei ist unveraendert",
        "service_untraced": "Kein Debugger ist am Originaldienst aktiv",
        "service_not_stopped": "Originaldienst ist nicht angehalten",
        "no_debugger": "Keine GDB-/GDB-Server-Prozesse laufen",
        "no_local_ota": "Kein lokales Firmwareupdate ist aktiv",
        "no_cloud_guard": "Keine lokale Cloud-Sperre ist aktiv",
        "cloud_connected": "Cloudverbindung ist hergestellt",
        "watchdogs_running": "Originale Ueberwachungsdienste laufen",
        "http_stopped": "Lokaler Firmware-Webserver ist beendet",
        "staging_clean": "Lokale Firmware-Zwischendateien sind entfernt",
        "helper_absent": "Temporärer Update-Helfer ist entfernt",
        "ota_info_valid": "OTA-Statusdatei ist gueltig",
    }
    for key, label in labels.items():
        ok = result["checks"][key]
        print(_paint(f"[OK] {label}" if ok else f"[FEHLER] {label}", GREEN if ok else RED), flush=True)
    summary = "Originalzustand vollstaendig bestaetigt" if result["original_ok"] else "Originalzustand nicht vollstaendig"
    print(_paint(f"[OK] {summary}" if result["original_ok"] else f"[FEHLER] {summary}",
                 GREEN if result["original_ok"] else RED), flush=True)


def validate_local_runtime_helper(path: Path) -> str:
    if not path.is_file():
        raise OtaError(f"local runtime helper not found: {path}")
    raw = path.read_bytes()
    if not raw.startswith(b"#!/bin/sh\n"):
        raise OtaError("local runtime helper has no valid /bin/sh header")
    required = (
        EXPECTED_BUILD_ID.encode(),
        EXPECTED_SERVICE_SHA256.lower().encode(),
        b"make_gdb_script()",
    )
    if any(marker not in raw for marker in required):
        raise OtaError("local runtime helper does not match the verified service build")
    return hashlib.sha256(raw).hexdigest()


def install_runtime_helper(adb: AdbClient, local_helper: Path, *, allow_active: bool = False) -> str:
    local_hash = validate_local_runtime_helper(local_helper)
    print_event("helper-local-verified", path=str(local_helper), sha256=local_hash)
    if not allow_active:
        active = any(
            adb.shell(f"test -f {marker}; echo $?") == "0"
            for marker in (REMOTE_RUN_ACTIVE, REMOTE_INJECTION_STARTED, REMOTE_TRANSFER_STARTED)
        )
        if active:
            raise OtaError("a local OTA state is active; refusing to replace its runtime helper")
    adb.shell(f"rm -f {REMOTE_HELPER_STAGE}")
    activated = False
    try:
        adb.push(local_helper, REMOTE_HELPER_STAGE)
        staged_hash = adb.shell(
            f"sha256sum {REMOTE_HELPER_STAGE} | awk '{{print $1}}'"
        ).lower()
        if staged_hash != local_hash:
            raise OtaError(f"staged runtime helper SHA256 mismatch: {staged_hash}")
        adb.shell(f"chmod 755 {REMOTE_HELPER_STAGE}")
        if adb.shell(f"test -x {REMOTE_HELPER_STAGE}; echo $?") != "0":
            raise OtaError("staged runtime helper is not executable")
        adb.shell(f"mv -f {REMOTE_HELPER_STAGE} {REMOTE_HELPER}")
        activated = True
        remote_hash = adb.shell(
            f"sha256sum {REMOTE_HELPER} | awk '{{print $1}}'"
        ).lower()
        if remote_hash != local_hash:
            raise OtaError(f"installed runtime helper SHA256 mismatch: {remote_hash}")
    except BaseException:
        adb.shell(f"rm -f {REMOTE_HELPER_STAGE}", check=False)
        if activated:
            adb.shell(f"rm -f {REMOTE_HELPER}", check=False)
        raise
    print_event("helper-installed", remote=REMOTE_HELPER, sha256=local_hash)
    return local_hash


def remove_runtime_helper(adb: AdbClient) -> None:
    adb.shell(f"rm -f {REMOTE_HELPER} {REMOTE_HELPER_STAGE}")
    if adb.shell(f"test -e {REMOTE_HELPER}; echo $?") == "0":
        raise OtaError("runtime helper could not be removed from the LTE modem")
    print_event("helper-removed", remote=REMOTE_HELPER)


def restore_original_runtime(adb: AdbClient, local_helper: Path) -> dict:
    # Do not parse OTA_INFO here: the original 0033 handler legitimately
    # truncates it before C350 completes, which is exactly when restore is
    # needed after a pre-transfer guarded hold.
    transfer_started = adb.shell(f"test -f {REMOTE_TRANSFER_STARTED}; echo $?") == "0"
    if transfer_started:
        raise OtaError(
            "firmware blocks have started; automatic restore is locked and the original service remains authoritative"
        )
    helper_present = adb.shell(f"test -x {REMOTE_HELPER}; echo $?") == "0"
    if not helper_present:
        install_runtime_helper(adb, local_helper, allow_active=True)
    else:
        local_hash = validate_local_runtime_helper(local_helper)
        remote_hash = adb.shell(
            f"sha256sum {REMOTE_HELPER} | awk '{{print $1}}'"
        ).lower()
        if remote_hash != local_hash:
            active = any(
                adb.shell(f"test -f {marker}; echo $?") == "0"
                for marker in (REMOTE_RUN_ACTIVE, REMOTE_INJECTION_STARTED)
            )
            if active:
                raise OtaError("active recovery helper differs from the local verified helper; refusing replacement")
            install_runtime_helper(adb, local_helper)
    adb.shell(f"{REMOTE_HELPER} restore-original --status {REMOTE_STATUS}")
    remove_local_ota_artifacts(adb, remove_helper=True)
    deadline = time.monotonic() + 15
    after = None
    while time.monotonic() < deadline:
        try:
            candidate = original_runtime_status(adb)
        except OtaError:
            candidate = None
        if candidate is not None:
            after = candidate
            if after["original_ok"]:
                break
        time.sleep(1)
    if after is None:
        raise OtaError("original runtime restoration could not be verified")
    if not after["original_ok"]:
        raise OtaError(f"original runtime restoration is incomplete: {after['checks']}")
    print_event("original-state-released")
    print_event("services-restored", **after)
    return after


def mqtt_tcp_established(netstat_output: str) -> bool:
    """Return whether filtered TCP/1883 netstat output contains an active connection."""
    return any("ESTABLISHED" in line for line in netstat_output.splitlines())


def preflight(adb: AdbClient, firmware: Path, require_helper: bool,
              manifest: FirmwareManifest) -> dict:
    checks: dict[str, object] = {}
    if not firmware.is_file():
        raise OtaError(f"firmware not found: {firmware}")
    checks["firmware_size"] = firmware.stat().st_size
    checks["firmware_md5"] = file_md5(firmware)
    checks["firmware_sha256"] = hashlib.sha256(firmware.read_bytes()).hexdigest().upper()
    checks["manifest"] = asdict(manifest)
    checks["firmware_ok"] = (
        checks["firmware_size"] == manifest.size
        and checks["firmware_md5"] == manifest.md5
        and checks["firmware_sha256"] == manifest.sha256
    )

    checks["adb_state"] = adb.run("get-state").strip()
    # The modem supervisor can restart the service between pidof and readlink.
    # Require one stable PID snapshot, but tolerate that harmless short race.
    service_pid = ""
    service_path = ""
    for attempt in range(3):
        pid_before = adb.shell("pidof phnixIot4G || true")
        path = adb.shell(
            "p=$(pidof phnixIot4G | awk '{print $1}'); "
            "test -n \"$p\" && readlink /proc/$p/exe || true"
        )
        pid_after = adb.shell("pidof phnixIot4G || true")
        if pid_before and pid_before == pid_after and path:
            service_pid, service_path = pid_after, path
            break
        if attempt < 2:
            time.sleep(0.25)
    checks["service_pid"] = service_pid
    checks["service_path"] = service_path
    checks["service_sha256"] = adb.shell(
        f"sha256sum {REMOTE_SERVICE} | awk '{{print $1}}'"
    ).upper()
    checks["service_binary_ok"] = checks["service_sha256"] == EXPECTED_SERVICE_SHA256
    checks["watchdog_pids"] = adb.shell(
        "ps | awk '$4 == \"{helloworld}\" {print $1}'"
    )
    checks["gdb_present"] = adb.shell("test -x /usr/bin/gdb; echo $?") == "0"
    checks["httpd_present"] = "httpd" in adb.shell("busybox --list") .splitlines()
    checks["mqtt_connection"] = adb.shell(
        "netstat -nt 2>/dev/null | awk '$4 ~ /:1883$/ || $5 ~ /:1883$/ {print}'"
    )
    checks["mqtt_established"] = mqtt_tcp_established(str(checks["mqtt_connection"]))
    checks["storage"] = adb.shell("df -k /cache /data 2>/dev/null || true")
    checks["info_writable"] = adb.shell(f"test -r {REMOTE_INFO} && test -w {REMOTE_INFO}; echo $?") == "0"
    checks["statistics_writable"] = adb.shell(
        f"test -r {REMOTE_STATISTICS} && test -w {REMOTE_STATISTICS}; echo $?"
    ) == "0"
    checks["helper_present"] = adb.shell(f"test -x {REMOTE_HELPER}; echo $?") == "0"
    checks["ota_info"] = asdict(parse_ota_info(adb.read_file(REMOTE_INFO)))
    checks["no_active_resume"] = (
        checks["ota_info"]["offset"] == 0 and checks["ota_info"]["length"] == 0
    )

    failures = []
    if not checks["firmware_ok"]:
        failures.append("firmware size/MD5 mismatch")
    if checks["adb_state"] != "device":
        failures.append("ADB device is not ready")
    if not checks["mqtt_established"]:
        failures.append(
            "Cloud/MQTT ist nicht verbunden. Das Firmwareupdate wird wegen des "
            "30-Minuten-Rebootmechanismus nicht gestartet."
        )
    if not checks["service_pid"]:
        failures.append("original phnixIot4G service is not running")
    if checks["service_path"] != REMOTE_SERVICE:
        failures.append(f"unexpected service executable: {checks['service_path']!r}")
    if not checks["service_binary_ok"]:
        failures.append("original service SHA256/build does not match the verified binary")
    if not checks["watchdog_pids"]:
        failures.append("helloworld service watchdog was not found")
    if not checks["gdb_present"] or not checks["httpd_present"]:
        failures.append("required modem gdb/busybox-httpd support is missing")
    if not checks["info_writable"] or not checks["statistics_writable"]:
        failures.append("persistent state files are not readable/writable")
    if not checks["ota_info"]["crc_ok"]:
        failures.append("OTA_INFO CRC is invalid")
    if not checks["no_active_resume"]:
        failures.append("an existing OTA/resume session is active")
    if require_helper and not checks["helper_present"]:
        failures.append("verified runtime hook helper is missing")
    checks["ok"] = not failures
    checks["failures"] = failures
    return checks


def save_remote_state(adb: AdbClient, state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=False)
    (state_dir / "phnixIot_device_OTA_INFO").write_bytes(adb.read_file(REMOTE_INFO))
    (state_dir / "phnixIot_device_statisic").write_bytes(adb.read_file(REMOTE_STATISTICS))
    manifest = {
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ota_info": asdict(parse_ota_info((state_dir / "phnixIot_device_OTA_INFO").read_bytes())),
    }
    (state_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def stage_firmware(adb: AdbClient, firmware: Path, manifest: FirmwareManifest) -> None:
    adb.shell(f"mkdir -p {REMOTE_STAGE_DIR}")
    adb.push(firmware, REMOTE_FIRMWARE)
    remote_md5 = adb.shell(f"md5sum {REMOTE_FIRMWARE} | awk '{{print $1}}'").upper()
    if remote_md5 != manifest.md5:
        raise OtaError(f"staged modem firmware MD5 mismatch: {remote_md5}")
    adb.shell(
        f"test -f {REMOTE_HTTP_PID} && kill $(cat {REMOTE_HTTP_PID}) 2>/dev/null || true; "
        f"busybox httpd -p 127.0.0.1:8081 -h {REMOTE_STAGE_DIR}; "
        f"pgrep -f '^busybox httpd -p 127.0.0.1:8081 ' | awk '{{print $1}}' > {REMOTE_HTTP_PID}"
    )
    served_md5 = adb.shell(
        f"curl -fsS {DEFAULT_FIRMWARE_URL} | md5sum | awk '{{print $1}}'"
    ).upper()
    if served_md5 != manifest.md5:
        raise OtaError(f"modem localhost HTTP firmware MD5 mismatch: {served_md5}")
    print_event("firmware-staged", remote=REMOTE_FIRMWARE, url=DEFAULT_FIRMWARE_URL)


def stop_local_http(adb: AdbClient) -> None:
    adb.shell(
        f"test -f {REMOTE_HTTP_PID} && kill $(cat {REMOTE_HTTP_PID}) 2>/dev/null || true; "
        "for p in $(ps | awk '$4 == \"busybox\" && $5 == \"httpd\" {print $1}'); do "
        "cmd=$(tr '\\000' ' ' < /proc/$p/cmdline 2>/dev/null || true); "
        "case \"$cmd\" in *\"httpd -p 127.0.0.1:8081\"*\"-h /data/phnix_local_ota\"*) "
        "kill $p 2>/dev/null || true ;; esac; done; "
        f"rm -f {REMOTE_HTTP_PID}",
        check=False,
    )


def remove_local_ota_artifacts(adb: AdbClient, *, remove_helper: bool = False) -> None:
    stop_local_http(adb)
    adb.shell(
        f"rm -rf {REMOTE_STAGE_DIR} {REMOTE_HOOK_STATE}; "
        f"rm -f {REMOTE_STATUS} {REMOTE_HANDSHAKE_TRACE} {REMOTE_HTTP_PID}"
    )
    if remove_helper:
        remove_runtime_helper(adb)


def remote_status(adb: AdbClient, *, allow_transient_info: bool = False) -> dict:
    status_text = adb.shell(f"cat {REMOTE_STATUS} 2>/dev/null || true")
    if status_text:
        try:
            hook = json.loads(status_text)
        except json.JSONDecodeError:
            complete = []
            for line in status_text.splitlines():
                try:
                    complete.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            if not complete:
                raise
            hook = complete[-1]
    else:
        hook = {"state": "hook-not-running"}
    raw_info = adb.read_file(REMOTE_INFO)
    if allow_transient_info and len(raw_info) != 220:
        info = {"transient": True, "length_bytes": len(raw_info), "crc_ok": False}
    else:
        info = asdict(parse_ota_info(raw_info))
    return {
        "hook": hook,
        "ota_info": info,
        "run_active": adb.shell(f"test -f {REMOTE_RUN_ACTIVE}; echo $?") == "0",
        "transfer_started": adb.shell(f"test -f {REMOTE_TRANSFER_STARTED}; echo $?") == "0",
        "service_pid": adb.shell("pidof phnixIot4G || true"),
        "debugger_pids": adb.shell("pidof gdbserver gdb || true"),
    }


def cancel_probe_plan(adb: AdbClient) -> dict:
    info = asdict(parse_ota_info(adb.read_file(REMOTE_INFO)))
    service_sha = adb.shell(
        f"sha256sum {REMOTE_SERVICE} | awk '{{print $1}}'"
    ).upper()
    service_pid = adb.shell("pidof phnixIot4G || true")
    watchdogs = adb.shell("ps | awk '$4 == \"{helloworld}\" {print $1}'")
    current = remote_status(adb)["hook"]
    blockers = []
    if not info["crc_ok"]:
        blockers.append("OTA_INFO CRC is invalid")
    if info["offset"] != 0 or info["length"] != 0:
        blockers.append("persistent OTA resume state is active")
    if service_sha != EXPECTED_SERVICE_SHA256:
        blockers.append("original service SHA256 does not match")
    if not service_pid or not watchdogs:
        blockers.append("service or supervisor watchdog is missing")
    if current.get("phase") == "guarded-hold":
        blockers.append("launcher is already in guarded-hold")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "payload": cancel_payload(),
        "service_pid": service_pid,
        "watchdog_pids": watchdogs.splitlines(),
        "ota_info": info,
        "live_send_enabled": False,
        "next_action": "explicit mainboard-test approval after breakpoint validation",
    }


def cancel_proof_ok(hook: dict) -> bool:
    return (
        hook.get("phase") == "cancelled"
        and hook.get("terminal") is True
        and hook.get("c36a_sent") is True
        and hook.get("c36c_status") == 1
        and hook.get("cancel_pending") is False
        and hook.get("board_ota_step") == 12
        and hook.get("normal_operation_verified") is True
    )


def pre_c5a8_proof_ok(hook: dict, trace: dict) -> bool:
    return (
        hook.get("phase") == "pre-c5a8-hold"
        and hook.get("terminal") is True
        and hook.get("c350_sent") is True
        and hook.get("c36e_status_1") is True
        and hook.get("c357_sent") is True
        and hook.get("c36e_status_2") is True
        and hook.get("c5a8_sent") is False
        and hook.get("board_ota_step") == 1
        and trace.get("c5a8_frames") == 0
        and trace.get("metadata_stable") is True
        and trace.get("ssid_match") is True
    )


def same_version_proof_ok(hook: dict) -> bool:
    """Require the complete C350 equal-build terminal proof."""
    return (
        hook.get("phase") == "c350-same-version"
        and hook.get("terminal") is True
        and hook.get("c350_sent") is True
        and hook.get("c36e_status") == 0
        and hook.get("ssid_match") is True
        and hook.get("c357_sent") is False
        and hook.get("c5a8_sent") is False
        and hook.get("state_restored") is True
        and hook.get("recovery_required") is False
    )


def validate_logger_checklist(value: dict) -> list[str]:
    blockers = []
    required_true = (
        "capture_started", "passive_only", "raw_hex_enabled",
        "timestamps_enabled", "crc_validation_enabled",
        "fragment_reassembly_enabled", "multi_frame_split_enabled",
        "secrets_masked", "c5a8_critical_alarm_enabled",
    )
    if value.get("schema") != "phnix-pre-c5a8-logger-v1":
        blockers.append("logger checklist schema mismatch")
    for field in required_true:
        if value.get(field) is not True:
            blockers.append(f"logger requirement is not confirmed: {field}")
    required_registers = {"C350", "C357", "C36E", "C36A", "C36C", "C5A8"}
    missing = sorted(required_registers - set(value.get("registers", [])))
    if missing:
        blockers.append("logger does not decode: " + ", ".join(missing))
    if not str(value.get("output_file", "")).strip():
        blockers.append("logger output_file is empty")
    return blockers


def real_test_plan(args, adb: AdbClient) -> dict:
    checks = preflight(adb, args.firmware, require_helper=False, manifest=args.firmware_manifest)
    checklist = json.loads(args.logger_checklist.read_text(encoding="utf-8"))
    blockers = list(checks["failures"])
    blockers.extend(validate_logger_checklist(checklist))
    return {
        "ready": not blockers,
        "blockers": blockers,
        "preflight": checks,
        "logger": {
            "schema": checklist.get("schema"),
            "output_file": checklist.get("output_file"),
            "registers": checklist.get("registers", []),
            "passive_only": checklist.get("passive_only"),
        },
        "planned_sequence": [
            "C350", "C36E_STATUS_1", "C357", "C36E_STATUS_2",
            "HARD_STOP_BEFORE_C5A8", "C36A", "C36C_STATUS_1", "STEP_12",
        ],
        "forbidden": ["C5A8", "PROMOTION", "FLASH_COPY", "BOOT_SWITCH"],
        "live_execution_enabled": False,
        "approval_required": True,
    }


def run_pre_c5a8_vm_test(args, adb: AdbClient) -> None:
    """Exercise handshake/cancel while remaining impossible on real hardware."""
    if adb.shell(f"test -f {REMOTE_SIM_MARKER}; echo $?") != "0":
        raise OtaError("pre-c5a8-vm-test is locked to the marked VM simulator")
    if not args.execute:
        print_event("pre-c5a8-vm-dry-run", message="No VM state was changed")
        return
    if args.confirm != "VM-PRE-C5A8-ONLY":
        raise OtaError("VM confirmation must be VM-PRE-C5A8-ONLY")
    checks = preflight(adb, args.firmware, require_helper=True, manifest=args.firmware_manifest)
    print_event("preflight", **checks)
    if not checks["ok"]:
        raise OtaError("preflight failed: " + "; ".join(checks["failures"]))

    safe_terminal = False
    try:
        adb.shell(f"{REMOTE_HELPER} handshake-probe --status {REMOTE_STATUS}")
        status = remote_status(adb)
        raw_trace = adb.shell(f"cat {REMOTE_HANDSHAKE_TRACE} 2>/dev/null || true")
        trace = json.loads(raw_trace) if raw_trace else {}
        print_event("pre-c5a8-proof", status=status, trace=trace)
        if not pre_c5a8_proof_ok(status["hook"], trace):
            raise OtaError("VM handshake did not prove a safe halt before C5A8")

        adb.shell(f"{REMOTE_HELPER} handshake-cancel --status {REMOTE_STATUS}")
        cancelled = remote_status(adb)
        print_event("pre-c5a8-cancel-proof", **cancelled)
        if not cancel_proof_ok(cancelled["hook"]):
            raise OtaError("VM handshake cancel did not reach the proven terminal state")
        safe_terminal = True
        print_event("pre-c5a8-vm-complete", message="C350/C357 simulated; zero C5A8 frames; cancel proven")
    except BaseException:
        adb.shell(f"{REMOTE_HELPER} hold --status {REMOTE_STATUS}", check=False)
        print_event("guarded-hold", message="VM handshake proof failed closed")
        raise
    finally:
        if safe_terminal:
            adb.shell(f"{REMOTE_HELPER} stop --status {REMOTE_STATUS}", check=False)


def run_same_version_test(args, adb: AdbClient) -> None:
    """Offer the verified V3.3 as 0033 and require C36E/status 0.

    The helper hard-stops at C357 and C5A8.  Persistent files are backed up
    both on the controller and inside the modem helper.
    """
    simulated = adb.shell(f"test -f {REMOTE_SIM_MARKER}; echo $?") == "0"
    expected_confirm = "VM-SAME-VERSION-ONLY" if simulated else "PHNIX-C350-SAME-V33"
    if not args.execute:
        checks = preflight(adb, args.firmware, require_helper=False, manifest=args.firmware_manifest)
        checks["local_helper_sha256"] = validate_local_runtime_helper(args.runtime_helper)
        print_event("same-version-dry-run", simulated=simulated, **checks)
        return
    if args.confirm != expected_confirm:
        raise OtaError(f"confirmation must be {expected_confirm}")
    if not simulated and args.logger_confirm != "PASSIVE-LOGGER-RUNNING":
        raise OtaError("live test requires --logger-confirm PASSIVE-LOGGER-RUNNING")

    checks = preflight(adb, args.firmware, require_helper=False, manifest=args.firmware_manifest)
    print_event("preflight", **checks)
    if not checks["ok"]:
        raise OtaError("preflight failed: " + "; ".join(checks["failures"]))
    install_runtime_helper(adb, args.runtime_helper)

    try:
        state_dir = args.state_dir / time.strftime("%Y%m%d-%H%M%S")
        save_remote_state(adb, state_dir)
        original_info = (state_dir / "phnixIot_device_OTA_INFO").read_bytes()
        original_statistics = (state_dir / "phnixIot_device_statisic").read_bytes()
        print_event("state-backed-up", directory=str(state_dir))
        stage_firmware(adb, args.firmware, args.firmware_manifest)
        payload = command_payload(DEFAULT_FIRMWARE_URL, args.firmware_manifest)
        with tempfile.TemporaryDirectory() as temp_dir:
            command_file = Path(temp_dir) / "ota-command.json"
            command_file.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            adb.push(command_file, REMOTE_COMMAND)
    except BaseException:
        remove_local_ota_artifacts(adb, remove_helper=True)
        raise

    action = "same-version-probe" if simulated else "c350-probe"
    helper_command = (
        f"{REMOTE_HELPER} {action} --command {REMOTE_COMMAND} --status {REMOTE_STATUS} "
        f"--live-confirm {expected_confirm} --logger-confirm "
        f"{args.logger_confirm or 'SIMULATOR'}"
    )
    # Never interpret a terminal record from an earlier diagnostic as the
    # result of the run that is about to start.
    adb.shell(f"rm -f {REMOTE_STATUS}")
    helper = adb.popen_shell(helper_command)
    deadline = time.monotonic() + args.timeout
    safe_terminal = False
    try:
        while time.monotonic() < deadline:
            status = remote_status(adb, allow_transient_info=True)
            print_event("same-version-status", **status)
            hook = status["hook"]
            if hook.get("phase") == "guarded-hold":
                raise OtaError("same-version test entered guarded hold")
            if hook.get("recovery_required") is True:
                raise OtaError(f"same-version guard triggered: {hook.get('phase')}")
            if hook.get("terminal") is True:
                if not same_version_proof_ok(hook):
                    raise OtaError(f"unexpected terminal proof: {hook}")
                if adb.read_file(REMOTE_INFO) != original_info:
                    raise OtaError("OTA_INFO was not restored byte-for-byte")
                if adb.read_file(REMOTE_STATISTICS) != original_statistics:
                    raise OtaError("statistics file was not restored byte-for-byte")
                safe_terminal = True
                print_event(
                    "same-version-complete", c36e_status=0,
                    c357_frames=0, c5a8_frames=0, persistent_state_restored=True,
                )
                return
            if helper.poll() is not None:
                time.sleep(0.2)
            time.sleep(args.poll_interval)
        raise OtaError("same-version test watchdog expired")
    except BaseException:
        if not safe_terminal:
            adb.shell(f"{REMOTE_HELPER} hold --status {REMOTE_STATUS}", check=False)
            print_event("guarded-hold", message="No safe equal-build terminal proof")
        raise
    finally:
        if safe_terminal:
            adb.shell(f"{REMOTE_HELPER} stop --status {REMOTE_STATUS}", check=False)
            remove_local_ota_artifacts(adb, remove_helper=True)
            print_event("original-state-released")
            runtime = verify_original_runtime(adb)
            if not runtime["ok"]:
                raise OtaError(f"original LTE runtime was not fully restored: {runtime}")
            print_event("services-restored", **runtime)


def run_update(args, adb: AdbClient) -> None:
    # A dry-run must remain useful before the build-specific modem helper exists.
    checks = preflight(adb, args.firmware, require_helper=False, manifest=args.firmware_manifest)
    checks["local_helper_sha256"] = validate_local_runtime_helper(args.runtime_helper)
    print_event("preflight", **checks)
    if not checks["ok"]:
        raise OtaError("preflight failed: " + "; ".join(checks["failures"]))
    if not args.execute:
        print_event("dry-run-complete", message="No modem or bus state was changed")
        return

    simulated = adb.shell(f"test -f {REMOTE_SIM_MARKER}; echo $?") == "0"
    expected_confirm = "VM-FULL-UPDATE" if simulated else "PHNIX-FULL-UPDATE"
    if args.confirm != expected_confirm:
        raise OtaError(f"confirmation must be {expected_confirm}")
    install_runtime_helper(adb, args.runtime_helper)

    try:
        state_dir = args.state_dir / time.strftime("%Y%m%d-%H%M%S")
        save_remote_state(adb, state_dir)
        print_event("state-backed-up", directory=str(state_dir))
        stage_firmware(adb, args.firmware, args.firmware_manifest)

        payload = command_payload(args.firmware_url, args.firmware_manifest)
        with tempfile.TemporaryDirectory() as temp_dir:
            command_file = Path(temp_dir) / "ota-command.json"
            command_file.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            adb.push(command_file, REMOTE_COMMAND)
    except BaseException:
        remove_local_ota_artifacts(adb, remove_helper=True)
        raise

    helper_command = (
        f"{REMOTE_HELPER} run --build-id {EXPECTED_BUILD_ID} "
        f"--command {REMOTE_COMMAND} --status {REMOTE_STATUS} "
        "--allow-publish 0023,0053,0083"
    )
    # A terminal record from a previous run must never be interpreted as the
    # result of the helper that is about to start. This mirrors the guarded
    # same-version path and closes the start-up race seen on the real modem.
    adb.shell(f"rm -f {REMOTE_STATUS}")
    print_event("hook-start", allowed_publish=["0023", "0053", "0083"])
    helper = adb.popen_shell(helper_command)

    phase_started = time.monotonic()
    previous_phase = None
    last_offset = -1
    safe_terminal = False
    guarded_hold = False
    transfer_started = False
    helper_exit_seen_at = None
    try:
        while True:
            # OTA_INFO is owned by the original service. A read can overlap a
            # rewrite, so intermediate values are observational only and must
            # never interrupt an active firmware transfer.
            status = remote_status(adb, allow_transient_info=True)
            hook = status["hook"]
            info = status["ota_info"]
            print_event("status", **status)
            observed_offset = info.get("offset") if info.get("crc_ok") is True else None
            if isinstance(observed_offset, int) and observed_offset != last_offset:
                last_offset = observed_offset

            phase = hook.get("phase", "unknown")
            if phase in {"c5a8", "success-report", "success"} or status.get("transfer_started") is True:
                transfer_started = True
            if phase != previous_phase:
                previous_phase = phase
                phase_started = time.monotonic()
                print_event("phase-change", phase=phase)
            if hook.get("terminal") is True:
                safe_terminal = phase in {
                    "success", "failed", "parser-rejected", "precondition-rejected",
                    "same-version",
                }
                if phase == "success":
                    if hook.get("board_ota_step") != 12:
                        safe_terminal = False
                        raise OtaError("success was reported without confirmed board_ota_step 12")
                    print_event("complete", offset=info.get("offset"), length=info.get("length"))
                    return
                if phase == "same-version":
                    print_event(
                        "warning",
                        message="Gleiche Firmware erkannt - keine Firmwaredaten uebertragen",
                    )
                    return
                raise OtaError(f"terminal OTA state: {phase}")
            if helper.poll() is not None:
                # The helper writes its terminal status immediately before it
                # exits. A poll can observe that exit while this iteration
                # still contains the preceding status snapshot.
                if helper_exit_seen_at is None:
                    helper_exit_seen_at = time.monotonic()
                if time.monotonic() - helper_exit_seen_at < 1.0:
                    time.sleep(args.poll_interval)
                    continue
                raise OtaError(f"runtime helper exited unexpectedly with code {helper.returncode}")

            now = time.monotonic()
            if phase == "c5a8":
                # From the first firmware block onward the original service is
                # authoritative. The controller observes but never times out,
                # pauses or cancels a transfer based on OTA_INFO progress.
                time.sleep(args.poll_interval)
                continue
            phase_limit = {
                "c350": args.handshake_timeout,
                "c357": args.handshake_timeout,
            }.get(phase, args.start_timeout)
            if now - phase_started > phase_limit:
                raise OtaError(f"phase watchdog expired in {phase}")
            time.sleep(args.poll_interval)
    except BaseException:
        if not safe_terminal and not transfer_started:
            adb.shell(f"{REMOTE_HELPER} hold --status {REMOTE_STATUS}", check=False)
            guarded_hold = True
            print_event(
                "guarded-hold",
                message="Active OTA was frozen fail-closed; cloud and watchdog guards remain active",
            )
        elif not safe_terminal:
            print_event(
                "monitoring-connection-lost",
                message="ADB monitoring was lost after C5A8; original service remains authoritative",
            )
        raise
    finally:
        if safe_terminal and helper.poll() is None:
            adb.shell(f"{REMOTE_HELPER} stop --status {REMOTE_STATUS}", check=False)
            try:
                helper.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print_event("warning", message="runtime helper did not exit within 10 seconds")
        if safe_terminal:
            remove_local_ota_artifacts(adb, remove_helper=True)
            print_event("hook-stopped")
            runtime = verify_original_runtime(adb)
            if not runtime["ok"]:
                raise OtaError(f"original LTE runtime was not fully restored: {runtime}")
            print_event("services-restored", **runtime)
        elif guarded_hold:
            print_event("manual-recovery-required", status=REMOTE_STATUS)


def cancel_update(args, adb: AdbClient) -> None:
    """Request a guarded cancel and require the complete terminal proof.

    The VM helper implements this contract.  The real build-specific helper
    intentionally refuses it until the live C36A/C36C breakpoints have been
    validated.  Therefore exposing this command does not silently enable a
    physical cancel path.
    """
    initial = remote_status(adb)
    hook = initial["hook"]
    print_event("cancel-preflight", **initial)
    if hook.get("phase") != "guarded-hold" or hook.get("recovery_required") is not True:
        raise OtaError("cancel requires an active guarded-hold state")
    if not args.execute:
        print_event("cancel-dry-run", message="No cancel request was sent")
        return
    if args.confirm != "CANCEL-PHNIX-OTA":
        raise OtaError("live cancel confirmation must be CANCEL-PHNIX-OTA")

    command = f"{REMOTE_HELPER} cancel --status {REMOTE_STATUS}"
    helper = adb.popen_shell(command)
    started = time.monotonic()
    safe_terminal = False
    helper_exit_seen_at = None
    try:
        while True:
            status = remote_status(adb)
            hook = status["hook"]
            print_event("cancel-status", **status)
            phase = hook.get("phase")
            if phase == "cancelled" and hook.get("terminal") is True:
                if not cancel_proof_ok(hook):
                    raise OtaError("cancel terminal state is missing required recovery proof")
                safe_terminal = True
                print_event("cancel-complete", proof=hook)
                return
            if helper.poll() is not None:
                if helper_exit_seen_at is None:
                    helper_exit_seen_at = time.monotonic()
                if time.monotonic() - helper_exit_seen_at < 1.0:
                    time.sleep(args.poll_interval)
                    continue
                raise OtaError(f"cancel helper exited before a safe terminal state: {helper.returncode}")
            if time.monotonic() - started > args.timeout:
                raise OtaError(f"cancel watchdog expired in {phase or 'unknown'}")
            time.sleep(args.poll_interval)
    except BaseException:
        adb.shell(f"{REMOTE_HELPER} hold --status {REMOTE_STATUS}", check=False)
        print_event("guarded-hold", message="Cancel was not fully proven; guards remain active")
        raise
    finally:
        if safe_terminal:
            adb.shell(f"{REMOTE_HELPER} stop --status {REMOTE_STATUS}", check=False)
            remove_local_ota_artifacts(adb, remove_helper=True)
            print_event("cancel-cleanup-complete")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adb", default=shutil.which("adb") or "adb")
    parser.add_argument("--serial")
    parser.add_argument(
        "--runtime-helper", type=Path,
        default=Path(__file__).resolve().with_name("phnix_ota_runtime_hook"),
        help="local build-specific helper; copied temporarily to the LTE modem",
    )
    parser.add_argument("--output", choices=("auto", "human", "json"), default="auto",
                        help="auto uses friendly output on a terminal and JSON when redirected")
    parser.add_argument("--no-color", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--manifest", type=Path, required=True)
    common.add_argument("--firmware", type=Path)

    sub.add_parser("preflight", parents=[common])
    sub.add_parser("status")
    sub.add_parser("cancel-probe-plan")
    handshake = sub.add_parser("pre-c5a8-vm-test", parents=[common])
    handshake.add_argument("--execute", action="store_true")
    handshake.add_argument("--confirm")
    real_plan = sub.add_parser("pre-c5a8-real-plan", parents=[common])
    real_plan.add_argument("--logger-checklist", type=Path, required=True)
    same = sub.add_parser("same-version-test", parents=[common])
    same.add_argument("--execute", action="store_true")
    same.add_argument("--confirm")
    same.add_argument("--logger-confirm")
    same.add_argument("--state-dir", type=Path, default=Path("phnix-ota-state"))
    same.add_argument("--poll-interval", type=float, default=0.5)
    same.add_argument("--timeout", type=float, default=30.0)
    cancel = sub.add_parser("cancel")
    cancel.add_argument("--execute", action="store_true")
    cancel.add_argument("--confirm")
    cancel.add_argument("--poll-interval", type=float, default=0.5)
    cancel.add_argument("--timeout", type=float, default=25.0)
    run = sub.add_parser("run")
    run.add_argument("--manifest", type=Path)
    run.add_argument("--firmware", type=Path)
    mode = run.add_mutually_exclusive_group()
    mode.add_argument("--check", choices=("status",))
    mode.add_argument("--restore", choices=("original",))
    run.add_argument("--firmware-url", default=DEFAULT_FIRMWARE_URL)
    run.add_argument("--execute", action="store_true")
    run.add_argument("--confirm")
    run.add_argument("--state-dir", type=Path, default=Path("phnix-ota-state"))
    run.add_argument("--poll-interval", type=float, default=2.0)
    run.add_argument("--start-timeout", type=float, default=60.0)
    run.add_argument("--handshake-timeout", type=float, default=20.0)
    run.add_argument("--block-timeout", type=float, default=25.0,
                     help="deprecated compatibility option; C5A8 is controlled by the original service")
    return parser


def main() -> int:
    global OUTPUT_MODE, COLOR_ENABLED
    args = build_parser().parse_args()
    OUTPUT_MODE = args.output
    COLOR_ENABLED = not args.no_color
    try:
        if getattr(args, "manifest", None) is not None:
            args.firmware_manifest = FirmwareManifest.load(args.manifest)
            args.firmware = args.firmware_manifest.resolve_firmware(args.manifest, args.firmware)
            args.firmware_manifest.validate_file(args.firmware)
        adb = AdbClient(args.adb, args.serial)
        if args.command == "preflight":
            result = preflight(adb, args.firmware, require_helper=False, manifest=args.firmware_manifest)
            if _human_output():
                if result["ok"]:
                    print_event("preflight", **result)
                else:
                    print_event("error", message="Vorpruefung fehlgeschlagen: " + "; ".join(result["failures"]))
            else:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["ok"] else 1
        if args.command == "status":
            print(json.dumps(remote_status(adb), indent=2, ensure_ascii=False))
            return 0
        if args.command == "cancel-probe-plan":
            plan = cancel_probe_plan(adb)
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return 0 if plan["ready"] else 1
        if args.command == "cancel":
            cancel_update(args, adb)
            return 0
        if args.command == "pre-c5a8-vm-test":
            run_pre_c5a8_vm_test(args, adb)
            return 0
        if args.command == "pre-c5a8-real-plan":
            plan = real_test_plan(args, adb)
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return 0 if plan["ready"] else 1
        if args.command == "same-version-test":
            run_same_version_test(args, adb)
            return 0
        if args.command == "run" and args.check == "status":
            result = original_runtime_status(adb)
            show_original_status(result)
            return 0 if result["original_ok"] else 1
        if args.command == "run" and args.restore == "original":
            result = restore_original_runtime(adb, args.runtime_helper)
            show_original_status(result)
            return 0
        if args.command == "run" and getattr(args, "manifest", None) is None:
            raise OtaError("run requires --manifest unless --check status or --restore original is used")
        run_update(args, adb)
        return 0
    except (OtaError, TransportError, ManifestError, OSError, json.JSONDecodeError) as error:
        print_event("error", message=str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
