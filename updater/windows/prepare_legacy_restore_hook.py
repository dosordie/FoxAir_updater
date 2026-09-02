from __future__ import annotations

import argparse
from pathlib import Path


SYSTEM_HEADER = b"#!/system/bin/sh\n"
LEGACY_HEADER = b"#!/bin/sh\n"


def normalize_shell_bytes(raw: bytes) -> bytes:
    """Normalize a shell payload to Unix LF without otherwise changing bytes."""
    if b"\x00" in raw:
        raise RuntimeError("runtime hook contains NUL bytes")
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def legacy_hook_bytes(raw: bytes) -> bytes:
    """Return the controller-compatible runtime hook with deterministic LF."""
    normalized = normalize_shell_bytes(raw)
    if normalized.startswith(LEGACY_HEADER):
        return normalized
    if normalized.startswith(SYSTEM_HEADER):
        return LEGACY_HEADER + normalized[len(SYSTEM_HEADER):]
    raise RuntimeError("canonical runtime hook has unexpected header")


def prepare(source: Path, output: Path) -> None:
    try:
        written = legacy_hook_bytes(source.read_bytes())
    except RuntimeError as error:
        raise RuntimeError(f"{error}: {source}") from error

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(written)

    verified = output.read_bytes()
    if verified != written:
        raise RuntimeError(f"legacy runtime hook write verification failed: {output}")
    if not verified.startswith(LEGACY_HEADER):
        raise RuntimeError(f"legacy runtime hook header verification failed: {output}")
    if b"\r" in verified:
        raise RuntimeError(f"legacy runtime hook still contains CR line endings: {output}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
