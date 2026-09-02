from __future__ import annotations

import argparse
from pathlib import Path


SYSTEM_HEADER = b"#!/system/bin/sh\n"
LEGACY_HEADER = b"#!/bin/sh\n"


def prepare(source: Path, output: Path) -> None:
    raw = source.read_bytes()
    if raw.startswith(LEGACY_HEADER):
        # Current canonical hook already uses the exact header required by the
        # legacy controller. Preserve it byte-for-byte.
        written = raw
        body = raw[len(LEGACY_HEADER):]
    elif raw.startswith(SYSTEM_HEADER):
        # Backward/forward compatibility for revisions where the autonomous
        # hook used Android's explicit system shell shebang.
        body = raw[len(SYSTEM_HEADER):]
        written = LEGACY_HEADER + body
    else:
        raise RuntimeError(f"canonical runtime hook has unexpected header: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(written)

    verified = output.read_bytes()
    if not verified.startswith(LEGACY_HEADER):
        raise RuntimeError(f"legacy runtime hook header verification failed: {output}")
    if verified[len(LEGACY_HEADER):] != body:
        raise RuntimeError("legacy runtime hook body changed while preparing restore helper")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
