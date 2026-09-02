#!/usr/bin/env python3
"""Windows release wrapper adding a bounded MQTT grace after restore.

The shared restore controller deliberately requires the full original runtime,
including an ESTABLISHED MQTT connection.  Real DTU testing showed that all
safety-critical original-state checks can already be true while MQTT reconnects
slightly later.  The legacy controller currently waits only 15 seconds.

This wrapper does not weaken that proof.  It runs the normal Windows safety
wrapper first.  Only when ``run --restore original`` returned non-zero does it
poll the existing read-only ``run --check status`` path for up to 120 seconds.
Success is accepted only when that unchanged status command reports
``original_ok: true``.  The Windows cache-backup state is then finalized exactly
as the normal successful restore path would do.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


MQTT_RESTORE_GRACE_SECONDS = 120.0
POLL_SECONDS = 2.0


def _value_after(args: list[str], option: str) -> str | None:
    try:
        index = args.index(option)
    except ValueError:
        return None
    if index + 1 >= len(args):
        return None
    return args[index + 1]


def _is_restore(args: list[str]) -> bool:
    return (
        "run" in args
        and "--restore" in args
        and _value_after(args, "--restore") == "original"
    )


def _last_json_object(text: str) -> dict | None:
    # ``run --check status`` emits one pretty-printed JSON object.  Try the
    # complete output first, then fall back to individual JSON lines so this
    # remains compatible with machine-event output variants.
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        return value
    for line in reversed(text.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _status_command(args: list[str], hardened: Path) -> list[str]:
    adb = _value_after(args, "--adb")
    command = [sys.executable, str(hardened)]
    if adb:
        command += ["--adb", adb]
    serial = _value_after(args, "--serial")
    if serial:
        command += ["--serial", serial]
    command += ["--output", "json", "--no-color", "run", "--check", "status"]
    return command


def _wait_for_full_original(args: list[str], hardened: Path) -> dict | None:
    deadline = time.monotonic() + MQTT_RESTORE_GRACE_SECONDS
    announced = False
    latest: dict | None = None
    while time.monotonic() < deadline:
        completed = subprocess.run(
            _status_command(args, hardened),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        parsed = _last_json_object(completed.stdout)
        if isinstance(parsed, dict):
            latest = parsed
            if parsed.get("original_ok") is True:
                print(
                    "[Update-Schutz] Originalzustand nach verzögertem MQTT-Wiederaufbau vollständig bestätigt.",
                    flush=True,
                )
                return parsed
            checks = parsed.get("checks")
            if (
                not announced
                and isinstance(checks, dict)
                and checks.get("cloud_connected") is False
                and all(value is True for key, value in checks.items() if key != "cloud_connected")
            ):
                announced = True
                print(
                    "[Update-Schutz] Originaldienst ist vollständig zurück; warte noch auf die MQTT-/Cloud-Verbindung "
                    f"(max. {int(MQTT_RESTORE_GRACE_SECONDS)} s).",
                    flush=True,
                )
        time.sleep(POLL_SECONDS)
    return latest


def main() -> int:
    args = sys.argv[1:]
    here = Path(__file__).resolve().parent
    core_wrapper_path = here / "phnix_windows_controller_wrapper_core.py"
    hardened = here / "phnix_local_ota_controller_hardened.py"
    if not core_wrapper_path.is_file() or not hardened.is_file():
        print("[Update-Schutz] FEHLER: Windows-Restore-Backend ist unvollständig.", file=sys.stderr)
        return 2

    # Import the existing Windows wrapper so all established cache safeguards
    # remain authoritative.
    import importlib.util

    spec = importlib.util.spec_from_file_location("foxair_windows_controller_core", core_wrapper_path)
    if spec is None or spec.loader is None:
        print("[Update-Schutz] FEHLER: Windows-Controller konnte nicht geladen werden.", file=sys.stderr)
        return 2
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)

    rc = core.main()
    if rc == 0 or not _is_restore(args):
        return rc

    # The normal restore already removed helpers/guards.  Do not rerun it just
    # because MQTT was a few seconds late; prove the complete state read-only.
    after = _wait_for_full_original(args, hardened)
    if not isinstance(after, dict) or after.get("original_ok") is not True:
        return rc

    # The inner Windows wrapper intentionally left the local cache backup
    # pending because its restore returned non-zero.  Complete exactly that
    # already-established success path now that full original_ok is proven.
    try:
        core.restore_update_cache(core.adb_command(args))
    except SystemExit as error:
        return int(error.code or 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
