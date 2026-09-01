"""Guarded restart of the original PHNIX LTE communication service."""

from __future__ import annotations

import time


RESTART_MARKERS = (
    "/tmp/phnix_ota_hook/run.active",
    "/tmp/phnix_ota_hook/transfer-started",
    "/tmp/phnix_ota_hook/original-service-owns",
)


def restart_phnix_iot_service(adb, *, timeout: float = 25.0, poll_interval: float = 1.0) -> str:
    for marker in RESTART_MARKERS:
        state = adb.shell(f"if [ -e '{marker}' ]; then echo PRESENT; else echo ABSENT; fi")
        if state != "ABSENT":
            if state == "PRESENT":
                raise RuntimeError(
                    "phnixIot4G kann während eines aktiven oder noch nicht sicher "
                    "abgeschlossenen Firmwareupdates nicht neu gestartet werden."
                )
            raise RuntimeError(f"OTA-Schutzmarker konnte nicht sicher geprüft werden: {marker}")
    old_pid = adb.shell("pidof phnixIot4G").split()
    if not old_pid or not old_pid[0].isdigit():
        raise RuntimeError("phnixIot4G-Prozess wurde nicht gefunden.")
    old_pid = old_pid[0]
    adb.shell(f"kill -TERM {old_pid}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        current = adb.shell("pidof phnixIot4G", check=False).split()
        if current and current[0].isdigit() and current[0] != old_pid:
            return (
                "phnixIot4G wurde erfolgreich neu gestartet.\n"
                f"Alte PID: {old_pid}\nNeue PID: {current[0]}"
            )
    raise RuntimeError("phnixIot4G-Neustart konnte nicht bestätigt werden.")


def wait_for_phnix_runtime_ready(
    adb, *, timeout: float = 25.0, poll_interval: float = 1.0,
) -> str:
    """Wait read-only for a stable service PID and its MQTT connection."""
    deadline = time.monotonic() + timeout
    stable_pid = ""
    stable_count = 0
    while time.monotonic() < deadline:
        pid = adb.shell("pidof phnixIot4G", check=False).split()
        current_pid = pid[0] if pid and pid[0].isdigit() else ""
        if current_pid and current_pid == stable_pid:
            stable_count += 1
        else:
            stable_pid = current_pid
            stable_count = 1 if current_pid else 0
        mqtt = adb.shell(
            "netstat -tn 2>/dev/null | awk '$4 ~ /:1883$/ || $5 ~ /:1883$/ {print}'",
            check=False,
        )
        if stable_count >= 2 and any("ESTABLISHED" in line for line in mqtt.splitlines()):
            return stable_pid
        time.sleep(poll_interval)
    raise RuntimeError(
        "phnixIot4G läuft nach dem Neustart noch nicht stabil mit wiederhergestellter MQTT-Verbindung."
    )
