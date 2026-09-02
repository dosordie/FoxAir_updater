from __future__ import annotations

import argparse
from pathlib import Path


CANONICAL_HEADER = b"#!/system/bin/sh\n"
LEGACY_HEADER = b"#!/bin/sh\n"


def prepare(source: Path, output: Path) -> None:
    raw = source.read_bytes()
    if not raw.startswith(CANONICAL_HEADER):
        raise RuntimeError(f"canonical runtime hook has unexpected header: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(LEGACY_HEADER + raw[len(CANONICAL_HEADER):])
    written = output.read_bytes()
    if not written.startswith(LEGACY_HEADER):
        raise RuntimeError(f"legacy runtime hook header verification failed: {output}")
    if written[len(LEGACY_HEADER):] != raw[len(CANONICAL_HEADER):]:
        raise RuntimeError("legacy runtime hook body changed while replacing shebang")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
