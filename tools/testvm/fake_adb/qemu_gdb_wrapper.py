#!/usr/bin/env python3
"""Apply QEMU-only breakpoint semantics before invoking real gdb-multiarch."""

import os
from pathlib import Path
import sys


REAL_GDB = Path("/opt/foxair-fake-adb/gdb-multiarch.real")


def patch_script(text: str) -> tuple[str, bool]:
    """Use hardware breakpoints only for the QEMU parser handoff points."""
    if (
        "file /data/phnixIot4G" not in text
        or "target remote 127.0.0.1:12345" not in text
        or "PHNIX yield pc=" not in text
    ):
        return text, False
    patched = text.replace("break *0x1fe40", "hbreak *0x1fe40", 1)
    patched = patched.replace("break *0x1ba04", "hbreak *0x1ba04", 1)
    # The proven Work-QEMU script deliberately operates on absolute
    # addresses without loading the ARM ELF into host GDB.  Loading it is not
    # required for this hook and makes GDB 16.3 internally crash while qemu
    # reports the service's many fork/exec events during parser continuation.
    patched = patched.replace("file /data/phnixIot4G\n", "", 1)
    return patched, patched != text


def main() -> int:
    if not REAL_GDB.is_file():
        print(f"QEMU gdb wrapper: real debugger missing: {REAL_GDB}", file=sys.stderr)
        return 127
    try:
        index = sys.argv.index("-x")
        script = Path(sys.argv[index + 1])
    except (ValueError, IndexError):
        script = None
    if script is not None:
        try:
            original = script.read_text(encoding="utf-8")
            patched, changed = patch_script(original)
            if changed:
                script.write_text(patched, encoding="utf-8")
                print("FOXAIR_QEMU_GDB_HARDWARE_HANDOFF enabled", file=sys.stderr)
        except OSError as exc:
            print(f"QEMU gdb wrapper: cannot patch {script}: {exc}", file=sys.stderr)
            return 126
    os.execv(str(REAL_GDB), [str(REAL_GDB), *sys.argv[1:]])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
