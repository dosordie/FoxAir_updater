#!/usr/bin/env python3
"""Create an isolated lab executable whose embedded CA is replaced in-place."""

import argparse
import hashlib
from pathlib import Path


CA_SLOT_SIZE = 1281
LAB_CA_OFFSETS = {
    "7c573431f0a67620d473419644a83a4f4dc04b8a91bde5923c74a63ba1eaedb7": 519104,
    "57b415b0143f598e81bccb9d5d5c4ee848df817b79dc1493c3cfdb6d8c96409c": 515732,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ca", required=True)
    args = parser.parse_args()
    source = Path(args.source).read_bytes()
    offset = LAB_CA_OFFSETS.get(hashlib.sha256(source).hexdigest())
    if offset is None:
        raise SystemExit("unsupported original build for offline lab TLS")
    ca = Path(args.ca).read_bytes()
    if not ca.endswith(b"\n"):
        ca += b"\n"
    replacement = ca + b"\0"
    if len(replacement) > CA_SLOT_SIZE:
        raise SystemExit(f"test CA needs {len(replacement)} bytes; slot has {CA_SLOT_SIZE}")
    end = offset + CA_SLOT_SIZE
    if len(source) < end or source[offset:offset + 27] != b"-----BEGIN CERTIFICATE-----":
        raise SystemExit("expected embedded PEM not found at documented offset")
    output = Path(args.output)
    if output.resolve() == Path(args.source).resolve():
        raise SystemExit("refusing to overwrite the original service")
    output.write_bytes(source[:offset] + replacement.ljust(CA_SLOT_SIZE, b"\0") + source[end:])
    output.chmod(0o755)


if __name__ == "__main__":
    main()
