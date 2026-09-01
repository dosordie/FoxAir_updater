#!/usr/bin/env python3
"""Create an isolated lab executable whose embedded CA is replaced in-place."""

import argparse
from pathlib import Path


CA_FILE_OFFSET = 0x07EBC0
CA_SLOT_SIZE = 1281


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ca", required=True)
    args = parser.parse_args()
    source = Path(args.source).read_bytes()
    ca = Path(args.ca).read_bytes()
    if not ca.endswith(b"\n"):
        ca += b"\n"
    replacement = ca + b"\0"
    if len(replacement) > CA_SLOT_SIZE:
        raise SystemExit(f"test CA needs {len(replacement)} bytes; slot has {CA_SLOT_SIZE}")
    end = CA_FILE_OFFSET + CA_SLOT_SIZE
    if len(source) < end or source[CA_FILE_OFFSET:CA_FILE_OFFSET + 27] != b"-----BEGIN CERTIFICATE-----":
        raise SystemExit("expected embedded PEM not found at documented offset")
    output = Path(args.output)
    output.write_bytes(source[:CA_FILE_OFFSET] + replacement.ljust(CA_SLOT_SIZE, b"\0") + source[end:])
    output.chmod(0o755)


if __name__ == "__main__":
    main()
