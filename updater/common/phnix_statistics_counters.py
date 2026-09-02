#!/usr/bin/env python3
"""Safely inspect and adjust selected persistent PHNIX statistics counters.

This is a companion to ``phnix_statistics_maintenance``.  It deliberately
reuses the proven service/watchdog/backup mechanics from that module, but
allows a small, explicitly whitelisted group of decoded uint32 counters to be
changed together in one maintenance restart.

The Power-Reset-t counter is special: phnixIot4G loads the persistent value at
startup and increments the counter in RAM before normal operation.  Therefore
the startup image must contain final-1 so the restarted service reaches the
requested final RAM value.  The startup increment is not immediately persisted,
so after the new service is verified this tool atomically normalizes the
persistent file back to the requested final value and then verifies file and
RAM together.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

for candidate in (Path(__file__).resolve().parents[2], Path.cwd()):
    if (candidate / "updater/common/adb_transport.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from updater.common.adb_transport import AdbClient
from updater.common.phnix_modem_info import STATISTICS_ADDRESS, read_process_memory
from updater.common import phnix_statistics_maintenance as core


STATISTICS_SIZE = core.STATISTICS_SIZE
CONFIRM_TOKEN = core.CONFIRM_TOKEN

COUNTERS: dict[str, tuple[int, str]] = {
    "dtu_ota": (0x20, "DTU-OTA-Vorgänge"),
    "mainboard_ota": (0x24, "Mainboard OTA-Vorgänge"),
    "power_reset": (0x28, "Dienststarts (Power-Reset-t)"),
    "active_reset": (0x2C, "Aktive Modem-Neustarts (Active-Reset-t)"),
}
POWER_RESET_KEY = "power_reset"
OUTPUT_MODE = "human"


class CounterMaintenanceError(core.MaintenanceError):
    pass


def emit(event: str, **fields) -> None:
    record = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, **fields}
    if OUTPUT_MODE == "json":
        print(json.dumps(record, ensure_ascii=False), flush=True)
        return
    if event == "inspect":
        values = fields.get("values") or {}
        print(
            ", ".join(f"{COUNTERS[key][1]}: {values.get(key)}" for key in COUNTERS),
            flush=True,
        )
    elif event == "complete":
        print("Persistente Statistikzähler erfolgreich geändert", flush=True)
    elif event == "error":
        print(f"FEHLER: {fields.get('message')}", flush=True)
    else:
        print(f"{event}: {fields}", flush=True)


def _check_raw(raw: bytes) -> None:
    if len(raw) != STATISTICS_SIZE:
        raise CounterMaintenanceError(
            f"statistics file has {len(raw)} bytes; expected {STATISTICS_SIZE}"
        )


def counter_value(raw: bytes, key: str) -> int:
    _check_raw(raw)
    if key not in COUNTERS:
        raise CounterMaintenanceError(f"unsupported statistics counter: {key}")
    offset = COUNTERS[key][0]
    return int.from_bytes(raw[offset : offset + 4], "little")


def counter_values(raw: bytes) -> dict[str, int]:
    return {key: counter_value(raw, key) for key in COUNTERS}


def validate_updates(updates: dict[str, int]) -> dict[str, int]:
    if not updates:
        raise CounterMaintenanceError("no counter value selected")
    checked: dict[str, int] = {}
    for key, value in updates.items():
        if key not in COUNTERS:
            raise CounterMaintenanceError(f"unsupported statistics counter: {key}")
        if not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
            raise CounterMaintenanceError(f"{key} must be uint32 (0..4294967295)")
        checked[key] = value
    if POWER_RESET_KEY in checked and checked[POWER_RESET_KEY] < 1:
        raise CounterMaintenanceError(
            "Power-Reset-t cannot be 0 while phnixIot4G is running; its startup increments the RAM counter once"
        )
    return checked


def prepare_patch(raw: bytes, updates: dict[str, int]) -> tuple[bytes, dict[str, int]]:
    """Return the startup image and desired post-start values.

    Requested values replace only the selected counters.  Power-Reset-t is
    always written one lower in the startup image because phnixIot4G increments
    it in RAM during startup.  The persistent file is normalized to the desired
    final value after the restarted service has been verified.
    """
    _check_raw(raw)
    checked = validate_updates(updates)
    desired = counter_values(raw)
    desired.update(checked)
    if desired[POWER_RESET_KEY] < 1:
        raise CounterMaintenanceError(
            "current Power-Reset-t is 0; final-value-preserving maintenance is not possible"
        )

    stored = dict(desired)
    stored[POWER_RESET_KEY] = desired[POWER_RESET_KEY] - 1

    patched = bytearray(raw)
    touched = set(checked)
    touched.add(POWER_RESET_KEY)
    for key in touched:
        offset = COUNTERS[key][0]
        patched[offset : offset + 4] = stored[key].to_bytes(4, "little")

    allowed = set()
    for key in touched:
        offset = COUNTERS[key][0]
        allowed.update(range(offset, offset + 4))
    for index, (before, after) in enumerate(zip(raw, patched)):
        if before != after and index not in allowed:
            raise CounterMaintenanceError(
                f"internal patch guard failed: byte 0x{index:02X} outside selected counter ranges changed"
            )
    return bytes(patched), desired


def finalize_power_reset_file(raw: bytes, desired_power_reset: int) -> bytes:
    """Normalize the persisted Power-Reset-t after the service startup increment.

    Directly after restart the persistent file may still contain final-1 while
    RAM already contains final.  Only the Power-Reset-t field may be changed
    here; all other bytes from the freshly pulled post-start file are preserved.
    """
    _check_raw(raw)
    if not isinstance(desired_power_reset, int) or not 1 <= desired_power_reset <= 0xFFFFFFFF:
        raise CounterMaintenanceError("desired Power-Reset-t must be uint32 >= 1")

    current = counter_value(raw, POWER_RESET_KEY)
    prestart = desired_power_reset - 1
    if current not in {prestart, desired_power_reset}:
        raise CounterMaintenanceError(
            "unexpected Power-Reset-t before persistence finalization: "
            f"file={current}, expected {prestart} or {desired_power_reset}"
        )
    if current == desired_power_reset:
        return raw

    patched = bytearray(raw)
    offset = COUNTERS[POWER_RESET_KEY][0]
    patched[offset : offset + 4] = desired_power_reset.to_bytes(4, "little")
    for index, (before, after) in enumerate(zip(raw, patched)):
        if before != after and not offset <= index < offset + 4:
            raise CounterMaintenanceError(
                f"internal finalization guard failed: byte 0x{index:02X} outside Power-Reset-t changed"
            )
    return bytes(patched)


def _replace_persistent_file_without_backup(
    adb: AdbClient, patched_local: Path, expected_sha: str
) -> None:
    """Atomically replace statistics while preserving the original rescue backup."""
    adb.push(patched_local, core.REMOTE_PAYLOAD)
    size = adb.shell(f"wc -c < {core.REMOTE_PAYLOAD}")
    payload_sha = adb.shell(
        f"sha256sum {core.REMOTE_PAYLOAD} | awk '{{print $1}}'"
    ).upper()
    if size.strip() != str(STATISTICS_SIZE) or payload_sha != expected_sha:
        raise CounterMaintenanceError("final persistence payload verification failed")

    adb.shell(
        f"cp -p {core.REMOTE_STATISTICS} {core.REMOTE_STAGE} && "
        f"cat {core.REMOTE_PAYLOAD} > {core.REMOTE_STAGE} && sync"
    )
    stage_sha = adb.shell(
        f"sha256sum {core.REMOTE_STAGE} | awk '{{print $1}}'"
    ).upper()
    if stage_sha != expected_sha:
        raise CounterMaintenanceError("final persistence stage verification failed")

    adb.shell(
        f"mv {core.REMOTE_STAGE} {core.REMOTE_STATISTICS} && "
        f"rm -f {core.REMOTE_PAYLOAD} && sync"
    )
    final_sha = adb.shell(
        f"sha256sum {core.REMOTE_STATISTICS} | awk '{{print $1}}'"
    ).upper()
    if final_sha != expected_sha:
        raise CounterMaintenanceError("final persistence SHA256 mismatch")


def _pull_values(adb: AdbClient, destination: Path) -> tuple[bytes, dict[str, int]]:
    raw = core.pull_exact(adb, core.REMOTE_STATISTICS, destination, STATISTICS_SIZE)
    return raw, counter_values(raw)


def inspect_command(adb: AdbClient) -> int:
    with tempfile.TemporaryDirectory(prefix="phnix-stat-counters-inspect-") as temp_name:
        temp = Path(temp_name)
        result = core.preflight(adb, temp)
        raw, values = _pull_values(adb, temp / "statistics-counters.bin")
    emit(
        "inspect",
        ok=result["ok"],
        checks=result["checks"],
        values=values,
        statistics_sha256=core.sha256_bytes(raw),
    )
    return 0 if result["ok"] else 2


def set_command(
    adb: AdbClient,
    updates: dict[str, int],
    *,
    execute: bool,
    confirm: str | None,
    backup_dir: Path,
) -> int:
    checked = validate_updates(updates)
    with tempfile.TemporaryDirectory(prefix="phnix-stat-counters-") as temp_name:
        temp = Path(temp_name)
        before = core.preflight(adb, temp)
        emit("preflight", ok=before["ok"], checks=before["checks"])
        if not before["ok"]:
            failed = ", ".join(name for name, ok in before["checks"].items() if not ok)
            raise CounterMaintenanceError("preflight failed: " + failed)

        _raw_before, values_before = _pull_values(adb, temp / "preflight-counters.bin")
        if not execute:
            emit("dry-run", current_values=values_before, target_values=checked)
            return 0
        if confirm != CONFIRM_TOKEN:
            raise CounterMaintenanceError(f"write requires --confirm {CONFIRM_TOKEN}")

        old_pid = int(before["service_pid"])
        watchdogs = list(before["watchdog_pids"])
        rescue_armed = False
        paused = False
        replaced = False
        try:
            core.arm_watchdog_rescue(adb, watchdogs)
            rescue_armed = True
            emit("rescue-armed", timeout_seconds=core.RESCUE_TIMEOUT_SECONDS)

            core.pause_watchdogs(adb, watchdogs)
            paused = True
            emit("watchdogs-paused", watchdog_pids=watchdogs)

            stop_method = core.stop_service_for_maintenance(adb, old_pid)
            emit("service-stopped", old_pid=old_pid, method=stop_method)
            time.sleep(0.15)

            final_path = temp / "final-statistics.bin"
            final_raw, stopped_values = _pull_values(adb, final_path)
            patched, desired_final = prepare_patch(final_raw, checked)

            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            backup_path = backup_dir / f"phnixIot_device_statisic.{stamp}.before-multi-counter.bin"
            shutil.copy2(final_path, backup_path)
            emit(
                "state-backed-up",
                path=str(backup_path),
                sha256=core.sha256_bytes(final_raw),
                values=stopped_values,
            )

            patched_path = temp / "patched-statistics.bin"
            patched_path.write_bytes(patched)
            patched_sha = core.sha256_bytes(patched)
            core.install_patched_file(adb, patched_path, patched_sha)
            replaced = True
            emit(
                "statistics-written",
                requested=checked,
                desired_final=desired_final,
                power_reset_prestart=counter_value(patched, POWER_RESET_KEY),
                sha256=patched_sha,
            )

            core.resume_watchdogs(adb, watchdogs)
            paused = False
            new_pid = core.wait_service_restored(adb, old_pid)

            # First verify the live counters.  The startup path increments
            # Power-Reset-t in RAM, while the persistent file may still hold
            # the deliberately pre-decremented startup value.
            try:
                ram_raw = read_process_memory(
                    adb,
                    new_pid,
                    STATISTICS_ADDRESS + COUNTERS["dtu_ota"][0],
                    16,
                    attempts=3,
                )
                ram_values = {
                    key: int.from_bytes(
                        ram_raw[offset - COUNTERS["dtu_ota"][0] : offset - COUNTERS["dtu_ota"][0] + 4],
                        "little",
                    )
                    for key, (offset, _label) in COUNTERS.items()
                }
            except Exception as exc:
                raise CounterMaintenanceError(f"RAM verification failed after restart: {exc}") from exc

            ram_mismatches = {
                key: {"expected": expected, "ram": ram_values.get(key)}
                for key, expected in desired_final.items()
                if ram_values.get(key) != expected
            }
            if ram_mismatches:
                raise CounterMaintenanceError(
                    "RAM counter verification mismatch after restart: "
                    + json.dumps(ram_mismatches, sort_keys=True)
                )

            poststart_raw, poststart_values = _pull_values(
                adb, temp / "poststart-statistics.bin"
            )
            finalized = finalize_power_reset_file(
                poststart_raw, desired_final[POWER_RESET_KEY]
            )
            if finalized != poststart_raw:
                finalized_path = temp / "finalized-statistics.bin"
                finalized_path.write_bytes(finalized)
                finalized_sha = core.sha256_bytes(finalized)
                _replace_persistent_file_without_backup(
                    adb, finalized_path, finalized_sha
                )
                emit(
                    "power-reset-persistence-finalized",
                    before=poststart_values[POWER_RESET_KEY],
                    after=desired_final[POWER_RESET_KEY],
                    sha256=finalized_sha,
                )

            verify_file, file_values = _pull_values(
                adb, temp / "verify-statistics.bin"
            )
            mismatches = {
                key: {
                    "expected": expected,
                    "file": file_values.get(key),
                    "ram": ram_values.get(key),
                }
                for key, expected in desired_final.items()
                if file_values.get(key) != expected or ram_values.get(key) != expected
            }
            if mismatches:
                raise CounterMaintenanceError(
                    "counter verification mismatch after restart: "
                    + json.dumps(mismatches, sort_keys=True)
                )

            core.cleanup_remote(adb)
            emit("service-restored", service_pid=new_pid, watchdog_pids=core.watchdog_pids(adb))
            emit(
                "complete",
                values=file_values,
                ram_values=ram_values,
                changed=checked,
                stop_method=stop_method,
                backup=str(backup_path),
                statistics_sha256=core.sha256_bytes(verify_file),
                power_reset_compensated=True,
                power_reset_persistence_finalized=True,
            )
            return 0
        except BaseException:
            if replaced and core.first_pid(adb) is None:
                core.restore_remote_backup(adb)
            raise
        finally:
            if paused:
                core.resume_watchdogs(adb, watchdogs)
            if rescue_armed:
                core.disarm_watchdog_rescue(adb)
            core.cleanup_remote(adb)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Read or safely change selected PHNIX persistent statistics counters via ADB"
    )
    p.add_argument("--adb", default="adb", help="adb/adb.exe path")
    p.add_argument("--serial", default=None)
    p.add_argument("--output", choices=("human", "json"), default="human")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="read-only preflight and selected persistent counters")
    set_p = sub.add_parser("set", help="set one or more whitelisted persistent uint32 counters")
    set_p.add_argument("--dtu-ota-count", type=int)
    set_p.add_argument("--mainboard-ota-count", type=int)
    set_p.add_argument("--power-reset-count", type=int)
    set_p.add_argument("--active-reset-count", type=int)
    set_p.add_argument("--execute", action="store_true")
    set_p.add_argument("--confirm", default=None)
    set_p.add_argument(
        "--backup-dir",
        type=Path,
        default=Path.home() / "FoxAir_LTE_Backup" / "statistics-maintenance",
    )
    return p


def _updates_from_args(args: argparse.Namespace) -> dict[str, int]:
    values = {
        "dtu_ota": args.dtu_ota_count,
        "mainboard_ota": args.mainboard_ota_count,
        "power_reset": args.power_reset_count,
        "active_reset": args.active_reset_count,
    }
    return {key: value for key, value in values.items() if value is not None}


def main(argv: list[str] | None = None) -> int:
    global OUTPUT_MODE
    args = parser().parse_args(argv)
    OUTPUT_MODE = args.output
    adb = AdbClient(args.adb, serial=args.serial)
    try:
        if args.command == "show":
            return inspect_command(adb)
        return set_command(
            adb,
            _updates_from_args(args),
            execute=args.execute,
            confirm=args.confirm,
            backup_dir=args.backup_dir,
        )
    except Exception as exc:
        emit("error", message=str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
