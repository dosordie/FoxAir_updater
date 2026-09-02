#!/usr/bin/env python3
"""Create a privacy-conscious diagnostic ZIP for autonomous DTU OTA runs.

Only an explicit text whitelist is collected. Firmware binaries, OTA_INFO,
statistics blobs and other arbitrary DTU files are intentionally excluded.
By default all runner attempts from the same calendar day as the selected run
are included so repeated update attempts can be diagnosed together.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

for candidate in (Path(__file__).resolve().parents[2], Path.cwd()):
    if (candidate / "updater/common/adb_transport.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from updater.common.adb_transport import AdbClient, TransportError
from updater.dtu_ota.client import REMOTE_BASE, RUN_ID_RE


TEXT_FILES = (
    "status.json",
    "result.json",
    "runner.log",
    "hook.log",
    "hook-status.json",
    "launcher.log",
    "package.json",
    "package.sha256",
    "served.md5",
    "state/SHA256SUMS",
)

_SECRET_PATTERNS = (
    (re.compile(r'(?i)("?(?:device_secret|deviceSecret)"?\s*[:=]\s*"?)[^"\s,}]+'), r"\1<REDACTED>"),
    (re.compile(r'(?i)("?(?:product_key|productKey)"?\s*[:=]\s*"?)[^"\s,}]+'), r"\1<REDACTED>"),
    (re.compile(r'(?i)(\b(?:imei|iccid|ccid|deviceCode)\b\s*[:=]\s*"?)[0-9]{10,22}'), r"\1<REDACTED>"),
    (re.compile(r'(?<![0-9])[0-9]{15,22}(?![0-9])'), "<REDACTED-ID>"),
)


def redact_text(text: str) -> str:
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def safe_decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _valid_run_id(value: str) -> str:
    value = value.strip()
    if not RUN_ID_RE.fullmatch(value):
        raise RuntimeError("invalid run_id returned by DTU")
    return value


def resolve_run_id(adb: AdbClient, requested: str | None) -> str:
    if requested:
        if not RUN_ID_RE.fullmatch(requested):
            raise RuntimeError("invalid requested run_id")
        return requested
    active = adb.shell(f"cat {REMOTE_BASE}/active.lock/run_id 2>/dev/null || true", check=False)
    if active:
        return _valid_run_id(active)
    last = adb.shell(f"cat {REMOTE_BASE}/last_run_id 2>/dev/null || true", check=False)
    if not last:
        raise RuntimeError("DTU has neither an active nor a last OTA run")
    return _valid_run_id(last)


def run_day(run_id: str) -> str | None:
    match = re.match(r"^(\d{8})-", run_id)
    return match.group(1) if match else None


def same_day_run_ids(adb: AdbClient, primary_run_id: str) -> list[str]:
    """Return all valid DTU runner IDs from the primary run's YYYYMMDD day."""
    day = run_day(primary_run_id)
    if not day:
        return [primary_run_id]
    raw = adb.shell(f"ls -1 '{REMOTE_BASE}/runs' 2>/dev/null || true", check=False)
    values: list[str] = []
    for line in raw.splitlines():
        value = line.strip()
        if value.startswith(day + "-") and RUN_ID_RE.fullmatch(value):
            values.append(value)
    if primary_run_id not in values:
        values.append(primary_run_id)
    return sorted(set(values))


def read_optional(adb: AdbClient, remote: str) -> tuple[bytes | None, str | None]:
    marker = adb.shell(f"if [ -f '{remote}' ]; then echo PRESENT; else echo ABSENT; fi", check=False)
    if marker.strip() != "PRESENT":
        return None, "missing"
    try:
        return adb.read_file(remote), None
    except TransportError as error:
        return None, str(error)


def system_snapshot(adb: AdbClient) -> str:
    command = r'''
SERVICE_PID=$(pidof phnixIot4G 2>/dev/null | awk '{print $1}')
echo "boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || true)"
echo "service_pids=$(pidof phnixIot4G 2>/dev/null || true)"
if [ -n "$SERVICE_PID" ]; then
  echo "service_state=$(awk '/^State:/ {print $2,$3}' /proc/$SERVICE_PID/status 2>/dev/null)"
  echo "service_tracer_pid=$(awk '/^TracerPid:/ {print $2}' /proc/$SERVICE_PID/status 2>/dev/null)"
fi
echo "service_sha256=$(sha256sum /data/phnixIot4G 2>/dev/null | awk '{print $1}')"
echo "data_free_kb=$(df -k /data 2>/dev/null | awk 'NR==2 {print $4}')"
echo "watchdog_pids=$(ps 2>/dev/null | awk '$4 == "{helloworld}" {print $1}' | tr '\n' ' ')"
for marker in run.active transfer-started original-service-owns; do
  if [ -e "/tmp/phnix_ota_hook/$marker" ]; then echo "hook_marker_$marker=present"; else echo "hook_marker_$marker=absent"; fi
done
'''
    return redact_text(adb.shell(command, check=False))


def _host_logs_for_day(directory: Path | None, day: str | None) -> list[Path]:
    if directory is None or day is None or not directory.is_dir():
        return []
    return sorted(
        path for path in directory.glob(f"FoxAir_Update_{day}-*.log")
        if path.is_file()
    )


def create_bundle(
    adb: AdbClient,
    output: Path,
    *,
    run_id: str | None = None,
    host_log: Path | None = None,
    host_log_dir: Path | None = None,
    app_version: str = "unknown",
) -> dict[str, object]:
    resolved = resolve_run_id(adb, run_id)
    run_ids = same_day_run_ids(adb, resolved)
    day = run_day(resolved)
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    included: list[str] = []
    missing: dict[str, str] = {}
    host_logs: list[str] = []
    with tempfile.NamedTemporaryFile(prefix="foxair-diagnostics-", suffix=".zip", delete=False, dir=output.parent) as tmp:
        temp_path = Path(tmp.name)
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for collected_run_id in run_ids:
                run_dir = f"{REMOTE_BASE}/runs/{collected_run_id}"
                prefix = f"dtu-runs/{collected_run_id}"
                for relative in TEXT_FILES:
                    remote = f"{run_dir}/{relative}"
                    data, error = read_optional(adb, remote)
                    missing_key = f"{collected_run_id}/{relative}"
                    if data is None:
                        missing[missing_key] = error or "unavailable"
                        continue
                    text = redact_text(safe_decode(data))
                    archive.writestr(f"{prefix}/{relative}", text)
                    included.append(missing_key)
                    # Keep the historical single-run path as a convenient alias
                    # for the primary/current run.
                    if collected_run_id == resolved:
                        archive.writestr(f"dtu-run/{relative}", text)

            snapshot = system_snapshot(adb) + "\n"
            archive.writestr("dtu-run/system_snapshot.txt", snapshot)
            archive.writestr(f"dtu-runs/{resolved}/system_snapshot.txt", snapshot)
            included.append(f"{resolved}/system_snapshot.txt")

            if host_log and host_log.is_file():
                text = redact_text(host_log.read_text(encoding="utf-8", errors="replace"))
                archive.writestr("host/foxair-updater.log", text)
                included.append("host/foxair-updater.log")

            for path in _host_logs_for_day(host_log_dir, day):
                text = redact_text(path.read_text(encoding="utf-8", errors="replace"))
                archive.writestr(f"host/day/{path.name}", text)
                host_logs.append(path.name)
                included.append(f"host/day/{path.name}")

            manifest = {
                "schema": "foxair-diagnostic-bundle-v2",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "app_version": app_version,
                "run_id": resolved,
                "run_day": day,
                "run_ids": run_ids,
                "host_logs": host_logs,
                "included": included,
                "missing": missing,
                "privacy": {
                    "firmware_included": False,
                    "ota_info_binary_included": False,
                    "statistics_binary_included": False,
                    "text_redaction_applied": True,
                },
            }
            archive.writestr("diagnostic_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        os.replace(temp_path, output)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return {
        "ok": True,
        "output": str(output),
        "run_id": resolved,
        "run_ids": run_ids,
        "run_day": day,
        "host_logs": host_logs,
        "included": included,
        "missing": missing,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FoxAir DTU OTA diagnostic ZIP exporter")
    parser.add_argument("--adb", default=shutil.which("adb") or "adb")
    parser.add_argument("--serial")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--host-log", type=Path)
    parser.add_argument("--host-log-dir", type=Path)
    parser.add_argument("--app-version", default="unknown")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    adb = AdbClient(args.adb, args.serial)
    try:
        result = create_bundle(
            adb,
            args.output,
            run_id=args.run_id,
            host_log=args.host_log,
            host_log_dir=args.host_log_dir,
            app_version=args.app_version,
        )
    except (RuntimeError, TransportError, OSError, zipfile.BadZipFile) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
