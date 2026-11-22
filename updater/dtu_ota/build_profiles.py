"""Exact, read-only identification of known PHNIX LTE-DTU service builds.

The manufacturer-visible V1.0/V1.2 string is NOT an integrity identifier.
Only a full SHA256 of /data/phnixIot4G selects a build.  V1.0 is deliberately
detect-only until its runtime hook, recovery paths, and real hardware tests pass.

This module never attaches GDB, writes device files, or performs OTA.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


SERVICE_PATH = "/data/phnixIot4G"
_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


@dataclass(frozen=True)
class DtuBuildProfile:
    key: str
    software_version: str
    service_sha256: str
    elf_build_id: str
    service_size: int
    ota_enabled: bool
    hook_filename: str | None
    # V1.2 is the original validated runner. These addresses are for the
    # readiness probe only; V1.0 values remain candidates pending live tests.
    dtu_run_step: int
    dtu_sta: int
    board_ota_step: int
    uart_send_flag: int
    has_statistics_file: bool


V12 = DtuBuildProfile(
    key="lte-v1.2-af4dcae1",
    software_version="V1.2",
    service_sha256="7c573431f0a67620d473419644a83a4f4dc04b8a91bde5923c74a63ba1eaedb7",
    elf_build_id="af4dcae12639bedce833ee5efa5da009777b6319",
    service_size=747440,
    ota_enabled=True,
    hook_filename="phnix_ota_runtime_hook",
    dtu_run_step=0x98903,
    dtu_sta=0x98904,
    board_ota_step=0x98A94,
    uart_send_flag=0x930DC,
    has_statistics_file=True,
)

V10 = DtuBuildProfile(
    key="lte-v1.0-d25ea21f",
    software_version="V1.0",
    service_sha256="57b415b0143f598e81bccb9d5d5c4ee848df817b79dc1493c3cfdb6d8c96409c",
    elf_build_id="d25ea21f8c4edc95c820c570da4a3399d8bd1cbc",
    service_size=745772,
    ota_enabled=False,  # HARD BLOCK: no validated live runtime hook yet.
    hook_filename="phnix_ota_runtime_hook_v10",
    dtu_run_step=0x129189,
    dtu_sta=0x12918A,
    board_ota_step=0x1292FC,
    uart_send_flag=0xA0728,
    has_statistics_file=False,
)

KNOWN_BUILDS = (V12, V10)


class DtuBuildIdentificationError(ValueError):
    """The DTU binary cannot be identified as an exact known build."""


def lookup_build(sha256: str) -> DtuBuildProfile:
    digest = sha256.strip().lower()
    if not _SHA256_RE.fullmatch(digest):
        raise DtuBuildIdentificationError(
            "DTU-Service-SHA256 konnte nicht sicher ausgelesen werden; kein OTA gestartet."
        )
    for profile in KNOWN_BUILDS:
        if profile.service_sha256 == digest:
            return profile
    raise DtuBuildIdentificationError(
        "Unbekannter phnixIot4G-Build (SHA256 "
        + digest + "); kein OTA gestartet. Bitte Diagnose sichern."
    )


def identify_adb(adb) -> DtuBuildProfile:
    """Only read the already-installed service hash over ADB.

    The caller must pin the result in its package; the DTU-side supervisor
    independently verifies the on-device hash again before an OTA run.
    """
    raw = adb.shell(
        "sha256sum '/data/phnixIot4G' 2>/dev/null | awk '{print $1}'"
    )
    return lookup_build(raw.strip())


def describe_build(profile: DtuBuildProfile) -> dict:
    return {
        "build": profile.key,
        "dtu_software_version": profile.software_version,
        "sha256": profile.service_sha256,
        "elf_build_id": profile.elf_build_id,
        "service_size": profile.service_size,
        "ota_enabled": profile.ota_enabled,
        "ota_status": "supported" if profile.ota_enabled else "experimental-blocked",
        "reason": "" if profile.ota_enabled else (
            "V1.0 erkannt: noch kein live validierter Runtime-Hook/Resume. "
            "OTA aus Sicherheitsgründen gesperrt."
        ),
    }
