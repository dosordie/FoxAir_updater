#!/usr/bin/env python3
"""Create a hash-pinned FoxAir firmware manifest for later review."""

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

for candidate in (Path(__file__).resolve().parents[2], Path.cwd()):
    if (candidate / "updater/common/firmware_manifest.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from updater.common.firmware_manifest import FirmwareManifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--software-code", required=True)
    parser.add_argument("--display-version", required=True)
    parser.add_argument("--target-ssid", required=True)
    parser.add_argument("--image-base", default="0x08050000")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.firmware.read_bytes()
    display = args.display_version
    wire = f"00{display[1]}{display[3]}" if len(display) == 4 else ""
    manifest = FirmwareManifest(
        schema="foxair-firmware-v1",
        firmware_file=args.firmware.name,
        software_code=args.software_code,
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
