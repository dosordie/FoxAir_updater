#!/usr/bin/env python3
"""Create a hash-pinned FoxAir firmware manifest for later review."""

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

for candidate in (Path(__file__).resolve().parents[2], Path.cwd()):
    if (candidate / "updater/common/firmware_manifest.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from updater.common.firmware_manifest import FirmwareManifest


DEFAULT_IMAGE_BASE = "0x08050000"
DEFAULT_TARGET_SSID = "0063"
IDENTITY_RE = re.compile(rb"(?<![0-9A-Z])([0-9A-Z]{8})(00[0-9]{2})(?![0-9A-Z])")


def _analyse_firmware_identity(raw: bytes, image_base: int) -> tuple[str, str, str, int]:
    """Return software_code, wire_version, display_version and file offset.

    The V3.3 reference image contains the active mainboard identity as one
    12-byte ASCII constant: 82400644 + 0033.  A neighbouring compatibility
    constant ends in 0000, so it is deliberately excluded.  We do not rely on
    the V3.3 file offset; a future image may move the constant.

    Fail closed if the format is absent or ambiguous.
    """
    if len(raw) < 8:
        raise ValueError("firmware is too small to contain a Cortex-M vector table")

    initial_sp = int.from_bytes(raw[0:4], "little")
    reset_vector = int.from_bytes(raw[4:8], "little")
    reset_address = reset_vector & ~1
    image_end = image_base + len(raw)

    if not 0x20000000 <= initial_sp < 0x20100000:
        raise ValueError(f"unexpected initial stack pointer 0x{initial_sp:08X}")
    if reset_vector & 1 == 0:
        raise ValueError(f"reset vector 0x{reset_vector:08X} is not a Thumb entry")
    if not image_base <= reset_address < image_end:
        raise ValueError(
            f"reset vector 0x{reset_vector:08X} is outside image range "
            f"0x{image_base:08X}..0x{image_end - 1:08X}"
        )

    candidates: list[tuple[str, str, str, int]] = []
    for match in IDENTITY_RE.finditer(raw):
        software_code = match.group(1).decode("ascii")
        wire_version = match.group(2).decode("ascii")
        if wire_version == "0000":
            # The V3.3 image has a second code-referenced 12-byte constant
            # 823003140000.  It is not the running firmware version identity.
            continue
        display_version = f"V{wire_version[2]}.{wire_version[3]}"
        candidates.append((software_code, wire_version, display_version, match.start()))

    if not candidates:
        raise ValueError(
            "no unambiguous 8-byte software code + non-zero 00xy wire version "
            "identity was found in the firmware"
        )
    if len(candidates) != 1:
        details = ", ".join(
            f"{code}{wire}@0x{offset:X}" for code, wire, _display, offset in candidates
        )
        raise ValueError(f"firmware identity is ambiguous: {details}")

    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument(
        "--full",
        action="store_true",
        help="extract software code/version from the firmware and validate the Cortex-M image",
    )
    parser.add_argument("--software-code")
    parser.add_argument("--display-version")
    parser.add_argument("--target-ssid", default=DEFAULT_TARGET_SSID)
    parser.add_argument("--image-base", default=DEFAULT_IMAGE_BASE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    raw = args.firmware.read_bytes()

    if args.target_ssid != DEFAULT_TARGET_SSID:
        parser.error(
            f"target_ssid is the fixed FoxAir Modbus unit address 0x63 and must be {DEFAULT_TARGET_SSID}"
        )

    software_code = args.software_code
    display = args.display_version

    if args.full:
        try:
            image_base = int(args.image_base, 0)
            detected_code, detected_wire, detected_display, detected_offset = _analyse_firmware_identity(
                raw, image_base
            )
        except ValueError as error:
            parser.error(str(error))

        if software_code is not None and software_code != detected_code:
            parser.error(
                f"--software-code {software_code} does not match firmware identity {detected_code}"
            )
        if display is not None and display != detected_display:
            parser.error(
                f"--display-version {display} does not match firmware identity {detected_display}"
            )

        software_code = detected_code
        display = detected_display
        wire = detected_wire
        print(
            f"detected firmware identity: software_code={software_code} "
            f"wire_version={wire} display_version={display} offset=0x{detected_offset:X}",
            file=sys.stderr,
        )
    else:
        if software_code is None:
            parser.error("--software-code is required unless --full is used")
        if display is None:
            parser.error("--display-version is required unless --full is used")
        wire = f"00{display[1]}{display[3]}" if len(display) == 4 else ""

    manifest = FirmwareManifest(
        schema="foxair-firmware-v1",
        firmware_file=args.firmware.name,
        software_code=software_code,
        display_version=display,
        wire_version=wire,
        target_ssid=args.target_ssid,
        size=len(raw),
        md5=hashlib.md5(raw).hexdigest().upper(),
        sha256=hashlib.sha256(raw).hexdigest().upper(),
        image_base=args.image_base,
    )
    manifest.validate_fields()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(asdict(manifest), indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
