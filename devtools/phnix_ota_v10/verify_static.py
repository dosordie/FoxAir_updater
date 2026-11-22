#!/usr/bin/env python3
"""Offline, read-only ELF verifier for the V1.0 hook candidate locations.

PASS is a *static identity check*, never a permission to run a real OTA.
No ADB, GDB, network, process attachment or firmware mutation is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

# Also work when launched directly from the tools directory.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from updater.dtu_ota.build_profiles import V10

DEFAULT_SITES = Path(__file__).with_name("v10_hook_sites_candidates.json")


def u16(raw: bytes, offset: int) -> int:
    return struct.unpack_from("<H", raw, offset)[0]


def u32(raw: bytes, offset: int) -> int:
    return struct.unpack_from("<I", raw, offset)[0]


def align4(value: int) -> int:
    return (value + 3) & ~3


def load_segments_and_build_id(raw: bytes):
    if len(raw) < 52 or raw[:6] != b"\x7fELF\x01\x01":
        raise ValueError("not an ELF32 little-endian executable")
    if u16(raw, 16) != 2 or u16(raw, 18) != 40:
        raise ValueError("not an ARM ET_EXEC")
    phoff, entsize, count = u32(raw, 28), u16(raw, 42), u16(raw, 44)
    if entsize < 32 or phoff + count * entsize > len(raw):
        raise ValueError("malformed program headers")
    segments = []
    build_id = None
    for i in range(count):
        pos = phoff + i * entsize
        p_type, foff, vaddr, _, fsize, msize, _, _ = struct.unpack_from("<8I", raw, pos)
        if foff + fsize > len(raw) or fsize > msize:
            raise ValueError("invalid segment bounds")
        if p_type == 1:
            segments.append((vaddr, foff, fsize))
        elif p_type == 4:
            cursor = foff
            end = foff + fsize
            while cursor + 12 <= end:
                namesz, descsz, typ = struct.unpack_from("<III", raw, cursor)
                cursor += 12
                if cursor + align4(namesz) + align4(descsz) > end:
                    raise ValueError("invalid note bounds")
                name = raw[cursor:cursor + namesz].rstrip(b"\x00")
                cursor += align4(namesz)
                desc = raw[cursor:cursor + descsz]
                cursor += align4(descsz)
                if typ == 3 and name == b"GNU":
                    build_id = desc.hex()
    if not segments or build_id is None:
        raise ValueError("ELF LOAD segments or GNU build-ID missing")
    return segments, build_id


def bytes_at(raw: bytes, segments, address: int, count: int) -> bytes:
    for vaddr, offset, length in segments:
        if vaddr <= address and address + count <= vaddr + length:
            start = offset + address - vaddr
            return raw[start:start + count]
    raise ValueError(f"address 0x{address:x} is outside file-backed LOAD segments")


def inspect(binary: Path, sites: Path = DEFAULT_SITES) -> dict:
    raw = binary.read_bytes()
    manifest = json.loads(sites.read_text(encoding="utf-8"))
    digest = hashlib.sha256(raw).hexdigest()
    if manifest.get("source_sha256") != V10.service_sha256 or manifest.get("build_id") != V10.elf_build_id:
        raise ValueError("candidate manifest does not match pinned V1.0 identity")
    # Fail before parsing a foreign binary or trusting any of its addresses.
    if digest != V10.service_sha256 or len(raw) != V10.service_size:
        return {"ok": False, "status": "foreign-binary", "sha256": digest, "size": len(raw)}
    segments, build_id = load_segments_and_build_id(raw)
    result = []
    for item in manifest["entries"]:
        address = int(item["v10_candidate"], 16)
        expected = bytes.fromhex(item["v10_machine_bytes_8"])
        if len(expected) != 8 or address % 4:
            raise ValueError("invalid signature entry")
        actual = bytes_at(raw, segments, address, 8)
        result.append({
            "name": item["name"],
            "address": f"0x{address:x}",
            "ok": actual == expected,
        })
    valid = build_id == V10.elf_build_id and len(result) == 18 and all(x["ok"] for x in result)
    return {
        "ok": valid,
        "status": "static-only-pass" if valid else "static-mismatch",
        "sha256": digest,
        "build_id": build_id,
        "size": len(raw),
        "signatures_ok": sum(x["ok"] for x in result),
        "signatures_total": len(result),
        "sites": result,
        "ota_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path, help="local original phnixIot4G V1.0 binary")
    parser.add_argument("--sites", type=Path, default=DEFAULT_SITES)
    args = parser.parse_args()
    try:
        result = inspect(args.binary, args.sites)
    except (ValueError, OSError, KeyError, TypeError, struct.error) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
