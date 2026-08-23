"""Build-locked runtime addresses for the verified ARM phnixIot4G service."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path


SERVICE_SHA256 = "7c573431f0a67620d473419644a83a4f4dc04b8a91bde5923c74a63ba1eaedb7"


@dataclass(frozen=True)
class BreakpointSite:
    name: str
    address: int
    instruction: bytes


CANCEL_BREAKPOINTS = (
    BreakpointSite("scheduler_injection", 0x1FDAC, bytes.fromhex("070000ea")),
    BreakpointSite("cancel_0073_handler", 0x19764, bytes.fromhex("00482de9")),
    BreakpointSite("c36a_send_call", 0x1DACC, bytes.fromhex("34f5ffeb")),
    BreakpointSite("c36c_handler", 0x1B51C, bytes.fromhex("00482de9")),
    BreakpointSite("cancel_pending_cleared", 0x1B5A8, bytes.fromhex("fc3808e3")),
    BreakpointSite("cancel_step10_setter", 0x1DB94, bytes.fromhex("ecfdffeb")),
    BreakpointSite("failure_publish_0083", 0x19264, bytes.fromhex("00482de9")),
    BreakpointSite("terminal_step12_complete", 0x1D748, bytes.fromhex("000000ea")),
)


def _virtual_to_file_offset(raw: bytes, address: int) -> int:
    if raw[:4] != b"\x7fELF" or raw[4] != 1 or raw[5] != 1:
        raise ValueError("expected a little-endian ELF32 binary")
    phoff = struct.unpack_from("<I", raw, 28)[0]
    phentsize, phnum = struct.unpack_from("<HH", raw, 42)
    for index in range(phnum):
        offset = phoff + index * phentsize
        p_type, p_offset, p_vaddr = struct.unpack_from("<III", raw, offset)
        p_filesz = struct.unpack_from("<I", raw, offset + 16)[0]
        if p_type == 1 and p_vaddr <= address < p_vaddr + p_filesz:
            return p_offset + address - p_vaddr
    raise ValueError(f"address 0x{address:x} is outside file-backed LOAD segments")


def verify_runtime_binary(path: str | Path) -> dict:
    raw = Path(path).read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest()
    checks = []
    for site in CANCEL_BREAKPOINTS:
        file_offset = _virtual_to_file_offset(raw, site.address)
        actual = raw[file_offset:file_offset + len(site.instruction)]
        checks.append({
            "name": site.name,
            "address": f"0x{site.address:x}",
            "expected": site.instruction.hex(),
            "actual": actual.hex(),
            "ok": actual == site.instruction,
        })
    return {
        "sha256": actual_sha,
        "sha256_ok": actual_sha == SERVICE_SHA256,
        "breakpoints": checks,
        "ok": actual_sha == SERVICE_SHA256 and all(item["ok"] for item in checks),
    }
