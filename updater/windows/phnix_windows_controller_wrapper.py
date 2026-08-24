#!/usr/bin/env python3
"""Windows-only safety wrapper around the shared PHNIX OTA controller.

This file deliberately does not implement OTA protocol logic. It mirrors the
Linux launcher safety shell around the controller:

* full firmware/manifest comparison immediately before an executed full update;
* backup of an existing /cache/phnixIot_device_OTA before update/same-version;
* keep that backup on a non-terminal/failed run;
* restore it after a successful same-version run or successful controller restore;
* distinguish a same-version terminal from a real update using host run-state;
* keep full-update run-state in a stable LOCALAPPDATA location.

All ADB calls are executed as argument lists. ADB_SERVER_SOCKET is inherited,
so the same wrapper works with the Windows GUI's Remote-ADB mode.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

REMOTE_CACHE = "/cache/phnixIot_device_OTA"
REMOTE_RESTORE_STAGE = "/cache/.phnixIot_device_OTA.restore"
COMPARE_FIELDS = (
    "schema",
    "firmware_file",
    "software_code",
    "display_version",
    "wire_version",
    "target_ssid",
    "size",
    "md5",
    "sha256",
    "image_base",
)


def fail(message: str, code: int = 2) -> NoReturn:
    print(f"[Windows-Sicherheitswrapper] FEHLER: {message}", file=sys.stderr, flush=True)
    raise SystemExit(code)


def note(message: str) -> None:
    print(f"[Windows-Sicherheitswrapper] {message}", flush=True)


def value_after(args: list[str], option: str) -> str | None:
    try:
        index = args.index(option)
    except ValueError:
        return None
    if index + 1 >= len(args):
        fail(f"Wert nach {option} fehlt")
    return args[index + 1]


def windows_app_state_root() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    path = base / "FoxAir Updater"
    path.mkdir(parents=True, exist_ok=True)
    return path


def windows_state_root() -> Path:
    path = windows_app_state_root() / "windows-wrapper-state" / "original-cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def windows_ota_state_root() -> Path:
    path = windows_app_state_root() / "ota-state"
    path.mkdir(parents=True, exist_ok=True)
    return path


def with_state_dir(args: list[str], state_dir: Path) -> list[str]:
    if "--state-dir" in args:
        return list(args)
    return [*args, "--state-dir", str(state_dir)]


def latest_update_phase(state_dir: Path) -> str:
    files = [path for path in state_dir.glob("*/run-state.json") if path.is_file()]
    if not files:
        fail("Terminaler Host-Run-State des Updates fehlt")
    latest = max(files, key=lambda path: path.stat().st_mtime_ns)
    try:
        value = json.loads(latest.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"Host-Run-State kann nicht gelesen werden: {exc}")
    phase = value.get("phase")
    if not isinstance(phase, str) or not phase:
        fail("Host-Run-State enthält keinen terminalen Phasenwert")
    return phase


def adb_command(args: list[str]) -> list[str]:
    adb = value_after(args, "--adb")
    if not adb:
        fail("--adb fehlt")
    return [adb]


def run_checked(command: list[str], *, binary: bool = False) -> str | bytes:
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr
        if binary and isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        fail(f"Befehl fehlgeschlagen ({completed.returncode}): {' '.join(command)}\n{str(stderr).strip()}")
    return completed.stdout


def adb_shell(base: list[str], command: str) -> str:
    out = run_checked([*base, "shell", command])
    assert isinstance(out, str)
    return out.replace("\r", "").strip()


def remote_file_exists(base: list[str], remote: str) -> bool:
    state = adb_shell(base, f"if [ -f '{remote}' ]; then echo PRESENT; else echo ABSENT; fi")
    if state == "PRESENT":
        return True
    if state == "ABSENT":
        return False
    fail(f"Unerwartete ADB-Antwort beim Prüfen von {remote}: {state or '<leer>'}")


def hash_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_paths() -> dict[str, Path]:
    root = windows_state_root()
    return {
        "root": root,
        "backup": root / "phnixIot_device_OTA",
        "present": root / "cache.present",
        "absent": root / "cache.absent",
        "pending": root / "cache.pending",
        "md5": root / "MD5",
        "sha256": root / "SHA256",
    }


def backup_update_cache(base: list[str]) -> None:
    paths = cache_paths()
    if paths["pending"].exists():
        fail(
            "Es existiert bereits ein offener Cache-Sicherungszustand. "
            "Zuerst den Zustand klären bzw. bei bestätigtem Pre-C5A8-Zustand Restore ausführen."
        )

    for key in ("backup", "present", "absent", "md5", "sha256"):
        try:
            paths[key].unlink()
        except FileNotFoundError:
            pass

    if remote_file_exists(base, REMOTE_CACHE):
        completed = subprocess.run(
            [*base, "pull", REMOTE_CACHE, str(paths["backup"])],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            fail(f"Vorhandene Cache-Firmware konnte nicht gesichert werden: {completed.stderr.strip()}")
        paths["md5"].write_text(hash_file(paths["backup"], "md5") + "\n", encoding="ascii")
        paths["sha256"].write_text(hash_file(paths["backup"], "sha256") + "\n", encoding="ascii")
        paths["present"].touch()
        note("Vorhandene LTE-Cache-Firmware vor dem OTA gesichert.")
    else:
        paths["absent"].touch()
        note(f"Vor dem OTA war keine Firmware unter {REMOTE_CACHE} vorhanden.")

    paths["pending"].touch()


def clear_cache_pending() -> None:
    try:
        cache_paths()["pending"].unlink()
    except FileNotFoundError:
        pass


def restore_update_cache(base: list[str]) -> None:
    paths = cache_paths()
    if not paths["pending"].exists():
        return

    if paths["present"].exists():
        if not paths["backup"].is_file() or not paths["sha256"].is_file():
            fail("Cache-Backup-Marker vorhanden, aber Sicherungsdatei/Hash fehlt")
        expected = paths["sha256"].read_text(encoding="ascii").strip().lower()

        run_checked([*base, "push", str(paths["backup"]), REMOTE_RESTORE_STAGE])
        remote_hash = adb_shell(base, f"sha256sum {REMOTE_RESTORE_STAGE} | awk '{{print $1}}'").lower()
        if remote_hash != expected:
            fail("SHA-256 der zurückkopierten Cache-Firmware stimmt nicht")

        adb_shell(base, f"mv {REMOTE_RESTORE_STAGE} '{REMOTE_CACHE}' && sync")
        remote_hash = adb_shell(base, f"sha256sum '{REMOTE_CACHE}' | awk '{{print $1}}'").lower()
        if remote_hash != expected:
            fail("SHA-256 der wiederhergestellten Cache-Firmware stimmt nicht")
        clear_cache_pending()
        note("Ursprüngliche LTE-Cache-Firmware wiederhergestellt.")
        return

    if paths["absent"].exists():
        adb_shell(base, f"rm -f '{REMOTE_CACHE}' {REMOTE_RESTORE_STAGE} && sync")
        clear_cache_pending()
        note("Ursprünglicher leerer LTE-Cache-Zustand wiederhergestellt.")
        return

    fail("Offener Cache-Sicherungszustand ist inkonsistent: present/absent Marker fehlt")


def resolve_manifest_firmware(manifest: Path) -> Path:
    try:
        expected = json.loads(manifest.read_text(encoding="utf-8"))
        name = expected["firmware_file"]
    except Exception as exc:
        fail(f"Ungültiges Manifest: {exc}")
    if not isinstance(name, str) or Path(name).name != name:
        fail("firmware_file muss ein einfacher Dateiname sein")
    firmware = manifest.parent / name
    if not firmware.is_file():
        fail(f"Zum Manifest gehörende Firmware nicht gefunden: {firmware}")
    return firmware


def full_manifest_preflight(manifest: Path, manifest_tool: Path) -> None:
    firmware = resolve_manifest_firmware(manifest)
    with tempfile.TemporaryDirectory(prefix="foxair-full-") as temp_dir:
        generated = Path(temp_dir) / "detected.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(manifest_tool),
                "--firmware",
                str(firmware),
                "--full",
                "--output",
                str(generated),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode != 0:
            fail("Vollanalyse der Firmware ist fehlgeschlagen:\n" + completed.stdout.strip())

        expected = json.loads(manifest.read_text(encoding="utf-8"))
        detected = json.loads(generated.read_text(encoding="utf-8"))
        errors = []
        for field in COMPARE_FIELDS:
            if expected.get(field) != detected.get(field):
                errors.append(
                    f"{field}: Manifest={expected.get(field)!r}, Firmware={detected.get(field)!r}"
                )
        if errors:
            fail("Manifest stimmt nicht mit der analysierten Firmware überein:\n  - " + "\n  - ".join(errors))
    note("Vollanalyse: Firmwareidentität, Größe und Hashes stimmen mit dem Manifest überein.")


def run_core(core: Path, args: list[str]) -> int:
    completed = subprocess.run([sys.executable, str(core), *args], check=False)
    return completed.returncode


def main() -> int:
    args = sys.argv[1:]
    here = Path(__file__).resolve().parent
    core = here / "phnix_local_ota_controller_hardened.py"
    manifest_tool = here / "create_firmware_manifest.py"
    if not core.is_file():
        fail(f"Gehärteter Controller fehlt: {core}")
    if not manifest_tool.is_file():
        fail(f"Manifest-Tool fehlt: {manifest_tool}")

    is_execute = "--execute" in args
    is_full_update = is_execute and "run" in args and "PHNIX-FULL-UPDATE" in args
    is_same = is_execute and "same-version-test" in args
    is_restore = "run" in args and "--restore" in args and value_after(args, "--restore") == "original"

    if is_full_update:
        base = adb_command(args)
        manifest_value = value_after(args, "--manifest")
        if not manifest_value:
            fail("--manifest fehlt beim Update")
        full_manifest_preflight(Path(manifest_value), manifest_tool)
        state_dir = windows_ota_state_root()
        run_args = with_state_dir(args, state_dir)
        backup_update_cache(base)
        rc = run_core(core, run_args)
        if rc == 0:
            phase = latest_update_phase(state_dir)
            if phase == "same-version":
                restore_update_cache(base)
                note("Gleichversion über normalen Updatepfad erkannt; ursprünglicher Cache wurde wiederhergestellt.")
            elif phase == "success":
                clear_cache_pending()
                note("Update terminal erfolgreich: offener Cache-Sicherungsmarker wurde gelöscht.")
            else:
                fail(f"Unerwarteter terminaler Updatezustand trotz Exit 0: {phase}")
        else:
            note(
                "Update nicht erfolgreich terminal beendet; das Original-Cache-Backup bleibt "
                "für einen gegebenenfalls zulässigen Pre-C5A8-Restore erhalten."
            )
        return rc

    if is_same:
        base = adb_command(args)
        backup_update_cache(base)
        rc = run_core(core, args)
        if rc == 0:
            restore_update_cache(base)
        else:
            note(
                "Gleichversionstest nicht sicher terminal beendet; Cache wird nicht automatisch verändert."
            )
        return rc

    if is_restore:
        base = adb_command(args)
        rc = run_core(core, args)
        if rc == 0:
            restore_update_cache(base)
        return rc

    return run_core(core, args)


if __name__ == "__main__":
    raise SystemExit(main())
