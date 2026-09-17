#!/usr/bin/env python3
"""Release diagnostic wrapper that excludes stale global GDB runtime logs.

The runtime hook stores GDB/GDBServer output below /tmp/phnix_ota_hook.  Those
paths are global to the DTU and may survive until the next reboot, so a later
run that never reached GDB must not accidentally archive a previous run's log.

This wrapper changes diagnostics only.  It does not signal, attach to, restart,
or otherwise modify the updater runner, runtime hook, or phnixIot4G service.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

for candidate in (Path(__file__).resolve().parents[2], Path.cwd()):
    if (candidate / "updater/common/adb_transport.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from updater.common.adb_transport import AdbClient, TransportError
from updater.dtu_ota import diagnostics as base


def _remote_mtime(adb: AdbClient, remote: str) -> int | None:
    """Read a remote mtime without changing the remote file.

    The target DTU already ships BusyBox.  If neither BusyBox nor the platform
    stat command can provide an epoch mtime, fail closed and do not attribute a
    global runtime log to the selected run.
    """
    raw = adb.shell(
        f"busybox stat -c %Y '{remote}' 2>/dev/null || "
        f"stat -c %Y '{remote}' 2>/dev/null || true",
        check=False,
    )
    for line in raw.splitlines():
        value = line.strip()
        if value.isdigit():
            return int(value)
    return None


def _run_reached_runtime_hook(adb: AdbClient, run_id: str) -> bool:
    run_dir = f"{base.REMOTE_BASE}/runs/{run_id}"
    marker = adb.shell(
        f"if [ -f '{run_dir}/hook.log' ] || [ -f '{run_dir}/hook-status.json' ]; "
        "then echo YES; else echo NO; fi",
        check=False,
    )
    return marker.strip() == "YES"


def runtime_files_for_run(adb: AdbClient, run_id: str) -> dict[str, str]:
    """Return only global runtime logs proven to belong to the selected run.

    runner.pid is written when the autonomous run starts and is not rewritten by
    later classify/status reconciliation.  A current GDB log must therefore be
    at least as new as that per-run file.  Requiring per-run hook evidence also
    prevents a same-version/preflight result from inheriting an older /tmp log.
    """
    if not _run_reached_runtime_hook(adb, run_id):
        return {}

    run_dir = f"{base.REMOTE_BASE}/runs/{run_id}"
    run_start_mtime = _remote_mtime(adb, f"{run_dir}/runner.pid")
    if run_start_mtime is None:
        return {}

    current: dict[str, str] = {}
    for archive_name, remote in base.LIVE_RUNTIME_TEXT_FILES.items():
        runtime_mtime = _remote_mtime(adb, remote)
        if runtime_mtime is not None and runtime_mtime >= run_start_mtime:
            current[archive_name] = remote
    return current


def main() -> int:
    args = base.build_parser().parse_args()
    adb = AdbClient(args.adb, args.serial)

    try:
        try:
            resolved = base.resolve_run_id(adb, args.run_id)
        except RuntimeError:
            resolved = None

        # Limit the base exporter to logs that can be tied to this exact run.
        # The process is one-shot, so changing this module-level whitelist has
        # no effect outside the diagnostic exporter process.
        if resolved is None:
            base.LIVE_RUNTIME_TEXT_FILES = {}
        else:
            base.LIVE_RUNTIME_TEXT_FILES = runtime_files_for_run(adb, resolved)

        result = base.create_bundle(
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
