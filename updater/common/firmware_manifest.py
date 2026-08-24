"""Validated firmware metadata used by every updater frontend."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


FOX_AIR_TARGET_SSID = "0063"


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class FirmwareManifest:
    schema: str
    firmware_file: str
    software_code: str
    display_version: str
    wire_version: str
    target_ssid: str
    size: int
    md5: str
    sha256: str
    image_base: str

    @classmethod
    def load(cls, path: Path) -> "FirmwareManifest":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            manifest = cls(**value)
        except (OSError, json.JSONDecodeError, TypeError) as error:
            raise ManifestError(f"invalid firmware manifest: {error}") from error
        manifest.validate_fields()
        return manifest

    def validate_fields(self) -> None:
        if self.schema != "foxair-firmware-v1":
            raise ManifestError("unsupported manifest schema")
        if Path(self.firmware_file).name != self.firmware_file:
            raise ManifestError("firmware_file must be a plain filename")
        if not re.fullmatch(r"[0-9A-Z]{8}", self.software_code):
            raise ManifestError("software_code must contain exactly 8 uppercase characters")
        if not re.fullmatch(r"V[0-9]\.[0-9]", self.display_version):
            raise ManifestError("display_version must use the Vn.n form")
        derived = f"00{self.display_version[1]}{self.display_version[3]}"
        if self.wire_version != derived:
            raise ManifestError(f"wire_version must be {derived} for {self.display_version}")
        if self.target_ssid != FOX_AIR_TARGET_SSID:
            raise ManifestError(
                f"target_ssid must be {FOX_AIR_TARGET_SSID} (FoxAir Modbus unit address 0x63)"
            )
        if not isinstance(self.size, int) or self.size <= 0:
            raise ManifestError("size must be a positive integer")
        if not re.fullmatch(r"[0-9A-F]{32}", self.md5):
            raise ManifestError("md5 must contain 32 uppercase hex digits")
        if not re.fullmatch(r"[0-9A-F]{64}", self.sha256):
            raise ManifestError("sha256 must contain 64 uppercase hex digits")
        if self.image_base != "0x08050000":
            raise ManifestError("unsupported image_base")

    def resolve_firmware(self, manifest_path: Path, override: Path | None = None) -> Path:
        firmware = override if override is not None else manifest_path.parent / self.firmware_file
        if firmware.name != self.firmware_file:
            raise ManifestError("firmware filename does not match manifest")
        return firmware

    def validate_file(self, firmware: Path) -> None:
        if not firmware.is_file():
            raise ManifestError(f"firmware not found: {firmware}")
        if firmware.stat().st_size != self.size:
            raise ManifestError("firmware size does not match manifest")
        md5 = hashlib.md5(firmware.read_bytes()).hexdigest().upper()
        sha256 = hashlib.sha256(firmware.read_bytes()).hexdigest().upper()
        if md5 != self.md5:
            raise ManifestError("firmware MD5 does not match manifest")
        if sha256 != self.sha256:
            raise ManifestError("firmware SHA256 does not match manifest")
