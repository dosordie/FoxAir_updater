"""Host-side construction and validation of immutable DTU OTA packages."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from updater.common.firmware_manifest import FirmwareManifest


PACKAGE_SCHEMA = "foxair-dtu-ota-package-v1"
RUNNER_VERSION = "1"
EXPECTED_SERVICE_SHA256 = "7C573431F0A67620D473419644A83A4F4DC04B8A91BDE5923C74A63BA1EAEDB7"
EXPECTED_SERVICE_BUILD_ID = "af4dcae12639bedce833ee5efa5da009777b6319"
RUN_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,96}")


class PackageError(ValueError):
    """An OTA package is incomplete, inconsistent, or unsafe."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def shell_payload_bytes(path: Path) -> bytes:
    """Return a shell payload with deterministic Unix line endings."""
    payload = path.read_bytes()
    if b"\x00" in payload:
        raise PackageError(f"shell payload contains NUL bytes: {path}")
    return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def ota_command_bytes(manifest: FirmwareManifest) -> bytes:
    value = {
        "cmd": "CMD_OTA", "code": "0033", "param": {
            "softwareCode": manifest.software_code,
            "softwareVer": manifest.display_version,
            "ssid": manifest.target_ssid,
            "fileMD5": manifest.md5,
            "fileSize": manifest.size,
            "otaFileDownloadAddr": "http://127.0.0.1:8081/firmware.bin",
        },
    }
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class DtuOtaPackage:
    value: dict[str, Any]

    @classmethod
    def build(
        cls,
        *,
        run_id: str,
        manifest: FirmwareManifest,
        firmware: Path,
        hook: Path,
        supervisor: Path,
        mode: str = "full",
        restart_service_before_update: bool = False,
        isolate_mqtt: bool = False,
        expected_service_sha256: str = EXPECTED_SERVICE_SHA256,
        expected_service_build_id: str = EXPECTED_SERVICE_BUILD_ID,
    ) -> "DtuOtaPackage":
        manifest.validate_file(firmware)
        value: dict[str, Any] = {
            "schema": PACKAGE_SCHEMA,
            "run_id": run_id,
            "firmware_file": "firmware.bin",
            "firmware_size": manifest.size,
            "firmware_md5": manifest.md5,
            "firmware_sha256": manifest.sha256,
            "software_code": manifest.software_code,
            "display_version": manifest.display_version,
            "wire_version": manifest.wire_version,
            "image_base": manifest.image_base,
            "target_ssid": manifest.target_ssid,
            "hook_file": "runtime_hook",
            "hook_version": f"phnix-runtime-{expected_service_build_id[:12]}",
            "hook_sha256": hashlib.sha256(shell_payload_bytes(hook)).hexdigest().upper(),
            "command_sha256": hashlib.sha256(ota_command_bytes(manifest)).hexdigest().upper(),
            "runner_file": "dtu_ota_supervisor.sh",
            "runner_version": RUNNER_VERSION,
            "runner_sha256": hashlib.sha256(shell_payload_bytes(supervisor)).hexdigest().upper(),
            "expected_service_sha256": expected_service_sha256.upper(),
            "expected_service_build_id": expected_service_build_id.lower(),
            "mode": mode,
            "restart_service_before_update": bool(restart_service_before_update),
            "isolate_mqtt": bool(isolate_mqtt),
            "minimum_free_margin_bytes": 1048576,
            "publish_allowlist": "0023,0053,0083",
        }
        package = cls(value)
        package.validate()
        return package

    def validate(self) -> None:
        value = self.value
        required = {
            "schema", "run_id", "firmware_file", "firmware_size", "firmware_md5",
            "firmware_sha256", "software_code", "display_version", "wire_version",
            "image_base", "target_ssid", "hook_file", "hook_version", "hook_sha256", "command_sha256",
            "runner_file", "runner_version", "runner_sha256", "expected_service_sha256",
            "expected_service_build_id", "mode", "restart_service_before_update",
            "isolate_mqtt", "minimum_free_margin_bytes", "publish_allowlist",
        }
        missing = sorted(required - value.keys())
        if missing:
            raise PackageError(f"package fields missing: {', '.join(missing)}")
        if value["schema"] != PACKAGE_SCHEMA:
            raise PackageError("unsupported package schema")
        if not RUN_ID_RE.fullmatch(str(value["run_id"])):
            raise PackageError("invalid run_id")
        for field, expected in (
            ("firmware_file", "firmware.bin"), ("hook_file", "runtime_hook"),
            ("runner_file", "dtu_ota_supervisor.sh"), ("target_ssid", "0063"),
            ("image_base", "0x08050000"), ("publish_allowlist", "0023,0053,0083"),
        ):
            if value[field] != expected:
                raise PackageError(f"unsafe {field}")
        if value["mode"] not in {"full", "same-version"}:
            raise PackageError("mode must be full or same-version")
        if not isinstance(value["firmware_size"], int) or value["firmware_size"] <= 0:
            raise PackageError("invalid firmware_size")
        if not isinstance(value["minimum_free_margin_bytes"], int) or value["minimum_free_margin_bytes"] < 0:
            raise PackageError("invalid minimum_free_margin_bytes")
        for field, length in (("firmware_md5", 32), ("firmware_sha256", 64),
                              ("hook_sha256", 64), ("command_sha256", 64), ("runner_sha256", 64),
                              ("expected_service_sha256", 64)):
            if not re.fullmatch(rf"[0-9A-F]{{{length}}}", str(value[field])):
                raise PackageError(f"invalid {field}")
        if not re.fullmatch(r"[0-9a-f]{40}", str(value["expected_service_build_id"])):
            raise PackageError("invalid expected_service_build_id")
        for field in ("restart_service_before_update", "isolate_mqtt"):
            if not isinstance(value[field], bool):
                raise PackageError(f"{field} must be boolean")

    def canonical_bytes(self) -> bytes:
        self.validate()
        return (json.dumps(self.value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest().upper()
