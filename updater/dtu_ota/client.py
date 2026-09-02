"""Reusable host client for the persistent DTU OTA runner contract."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from updater.common.adb_transport import AdbClient, TransportError
from updater.common.firmware_manifest import FirmwareManifest

from .package import DtuOtaPackage, RUN_ID_RE, ota_command_bytes, shell_payload_bytes


REMOTE_BASE = "/data/foxair_ota_runner"


class RunnerClientError(RuntimeError):
    pass


def _run_id(value: str) -> str:
    if not RUN_ID_RE.fullmatch(value):
        raise RunnerClientError("invalid run_id")
    return value


class DtuOtaClient:
    def __init__(self, adb: AdbClient, *, source_root: Path | None = None):
        self.adb = adb
        self.source_root = source_root or Path(__file__).resolve().parents[2]
        self.supervisor = self.source_root / "tools/dtu_ota_runner/dtu_ota_supervisor.sh"
        self.hook = self.source_root / "tools/phnix_ota/phnix_ota_runtime_hook"

    def _run_dir(self, run_id: str) -> str:
        return f"{REMOTE_BASE}/runs/{_run_id(run_id)}"

    def current_run_id(self) -> str:
        active = self.active_run_id()
        if active is not None:
            return active
        value = self.adb.shell(f"cat {REMOTE_BASE}/last_run_id 2>/dev/null || true")
        if not value:
            raise RunnerClientError("DTU has no last_run_id")
        return _run_id(value.strip())

    def active_run_id(self) -> str | None:
        value = self.adb.shell(f"cat {REMOTE_BASE}/active.lock/run_id 2>/dev/null || true")
        if not value:
            return None
        run_id = _run_id(value.strip())
        raw = self.adb.shell(
            f"cat '{self._run_dir(run_id)}/status.json' 2>/dev/null || true"
        )
        try:
            status = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            raise RunnerClientError(f"active lock for {run_id} has no valid status")
        if (
            status.get("schema") != "foxair-dtu-ota-run-v1"
            or status.get("run_id") != run_id
            or status.get("terminal") is True
        ):
            raise RunnerClientError(f"active lock for {run_id} is inconsistent with its status")
        return run_id

    def prepare(
        self,
        *,
        manifest_path: Path,
        firmware_path: Path | None = None,
        run_id: str | None = None,
        mode: str = "full",
        restart_service_before_update: bool = False,
        isolate_mqtt: bool = False,
    ) -> dict[str, Any]:
        active = self.active_run_id()
        if active is not None:
            raise RunnerClientError(f"active DTU OTA run blocks prepare: {active}")
        run_id = _run_id(run_id or time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns() % 10000:04d}")
        manifest = FirmwareManifest.load(manifest_path)
        firmware = manifest.resolve_firmware(manifest_path, firmware_path)
        package = DtuOtaPackage.build(
            run_id=run_id, manifest=manifest, firmware=firmware, hook=self.hook,
            supervisor=self.supervisor, mode=mode,
            restart_service_before_update=restart_service_before_update,
            isolate_mqtt=isolate_mqtt,
        )
        run_dir = self._run_dir(run_id)
        payload = f"{run_dir}/payload"
        self.adb.shell(f"mkdir -p '{payload}' '{run_dir}/state'")
        with tempfile.TemporaryDirectory() as temp:
            supervisor_path = Path(temp) / "dtu_ota_supervisor.sh"
            supervisor_path.write_bytes(shell_payload_bytes(self.supervisor))
            hook_path = Path(temp) / "runtime_hook"
            hook_path.write_bytes(shell_payload_bytes(self.hook))
            package_path = Path(temp) / "package.json"
            package_path.write_bytes(package.canonical_bytes())
            command_path = Path(temp) / "ota-command.json"
            command_path.write_bytes(ota_command_bytes(manifest))
            self.adb.push(supervisor_path, f"{payload}/dtu_ota_supervisor.sh")
            self.adb.push(hook_path, f"{payload}/runtime_hook")
            self.adb.push(firmware, f"{payload}/firmware.bin")
            self.adb.push(package_path, f"{run_dir}/package.json")
            self.adb.push(command_path, f"{payload}/ota-command.json")
        self.adb.shell(
            f"printf '%s\\n' '{package.sha256}' > '{run_dir}/package.sha256'; "
            f"chmod 700 '{payload}/dtu_ota_supervisor.sh' '{payload}/runtime_hook'"
        )
        try:
            self.adb.shell(
                f"SH=/system/bin/sh; test -x \"$SH\" || SH=/bin/sh; "
                f"\"$SH\" '{payload}/dtu_ota_supervisor.sh' preflight '{run_id}'"
            )
        except TransportError as error:
            try:
                rejected = self.status(run_id, reconcile=False)
            except (RunnerClientError, TransportError, OSError, ValueError):
                raise error
            reason = rejected.get("reason") or rejected.get("phase") or "preflight_failed"
            detail = rejected.get("detail") or str(error)
            raise RunnerClientError(f"DTU preflight rejected ({reason}): {detail}") from error
        return self.status(run_id, reconcile=False)

    def start(self, run_id: str) -> dict[str, Any]:
        run_dir = self._run_dir(run_id)
        command = (
            f"SH=/system/bin/sh; test -x \"$SH\" || SH=/bin/sh; "
            f"setsid \"$SH\" '{run_dir}/payload/dtu_ota_supervisor.sh' run '{run_id}' "
            f"</dev/null >>'{run_dir}/launcher.log' 2>&1 & sleep 1"
        )
        self.adb.shell(command)
        return self.status(run_id, reconcile=False)

    def status(self, run_id: str | None = None, *, reconcile: bool = True) -> dict[str, Any]:
        run_id = _run_id(run_id or self.current_run_id())
        run_dir = self._run_dir(run_id)
        if reconcile:
            self.adb.shell(
                f"SH=/system/bin/sh; test -x \"$SH\" || SH=/bin/sh; "
                f"\"$SH\" '{run_dir}/payload/dtu_ota_supervisor.sh' classify '{run_id}'",
                check=False,
            )
        raw = self.adb.shell(f"cat '{run_dir}/status.json'")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RunnerClientError(f"invalid DTU status JSON: {error}") from error
        required = {"schema", "run_id", "state", "phase", "terminal", "updated_at",
                    "transfer_started", "original_service_authoritative", "abort_allowed", "recovery",
                    "service_restart_requested", "service_restart_verified",
                    "mqtt_isolation_requested", "mqtt_isolated", "boot_id"}
        missing = sorted(required - value.keys())
        if missing or value.get("schema") != "foxair-dtu-ota-run-v1" or value.get("run_id") != run_id:
            raise RunnerClientError(f"invalid status contract (missing={missing})")
        return value

    def log(self, run_id: str | None = None) -> str:
        run_id = _run_id(run_id or self.current_run_id())
        return self.adb.shell(f"cat '{self._run_dir(run_id)}/runner.log' 2>/dev/null || true")

    def abort_request(self, run_id: str | None = None) -> dict[str, Any]:
        run_id = _run_id(run_id or self.current_run_id())
        self.adb.shell(f"touch '{self._run_dir(run_id)}/abort.request'")
        return self.status(run_id, reconcile=False)

    def _lifecycle(self, action: str, run_id: str | None = None) -> dict[str, Any] | None:
        run_id = _run_id(run_id or self.current_run_id())
        run_dir = self._run_dir(run_id)
        self.adb.shell(
            f"SH=/system/bin/sh; test -x \"$SH\" || SH=/bin/sh; "
            f"\"$SH\" '{run_dir}/payload/dtu_ota_supervisor.sh' {action} '{run_id}'"
        )
        if action == "cleanup":
            return None
        return self.status(run_id, reconcile=False)

    def acknowledge(self, run_id: str | None = None) -> dict[str, Any]:
        value = self._lifecycle("ack", run_id)
        assert value is not None
        return value

    def cleanup(self, run_id: str | None = None) -> None:
        self._lifecycle("cleanup", run_id)
