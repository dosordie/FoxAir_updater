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
    # QEMU's remote stub becomes unstable when GDB disables the currently hit
    # persistent hardware breakpoint from inside its own command list.  Make
    # the yield stop a one-shot hardware breakpoint instead; GDB removes it as
    # part of the stop event before the parser hand-off continues.
    patched = text.replace("break *0x1fe40", "thbreak *0x1fe40", 1)
    patched = patched.replace("break *0x1ba04", "hbreak *0x1ba04", 1)
    patched = patched.replace("  disable 1\n  set $return_pc = $pc", "  set $return_pc = $pc", 1)
    # The proven Work-QEMU script deliberately operates on absolute
    # addresses without loading the ARM ELF into host GDB.  Loading it is not
    # required for this hook and makes GDB 16.3 internally crash while qemu
    # reports the service's many fork/exec events during parser continuation.
    patched = patched.replace("file /data/phnixIot4G\n", "", 1)
    # qemu-user's single GDB stub cannot survive an execve() in one of the
    # inferior's forked children.  The original 0033 parser executes two
    # system() calls here (cache removal and OTA_INFO truncation), causing the
    # otherwise healthy remote target to disappear before C350.  Reproduce
    # those two file mutations in the VM namespace and temporarily intercept
    # system@plt while the injected parser is active.  One guarded hardware
    # breakpoint also stays within qemu-user's four-slot limit; two separate
    # call-site breakpoints exceeded it and made GDB fall back to an impossible
    # text-memory write.  This is strictly a QEMU transport workaround; the
    # uploaded production hook remains unchanged.
    patched = patched.replace(
        "set $resume_mode = 0\n",
        "set $resume_mode = 0\nset $foxair_parser_injected = 0\n",
        1,
    )
    c36e_anchor = "hbreak *0x1ba04\n"
    system_guards = """hbreak *0x1ba04
hbreak *0x9a98
condition 4 $foxair_parser_injected == 1
commands 4
  silent
  set $r0 = 0
  set $pc = $lr
  continue
end
"""
    patched = patched.replace(c36e_anchor, system_guards, 1)
    yield_anchor = "  set $return_pc = $pc\n"
    yield_patch = (
        "  shell rm -f /cache/phnixIot_device_OTA\n"
        "  shell : > /data/phnixIot_device_OTA_INFO\n"
        "  set $foxair_parser_injected = 1\n"
        + yield_anchor
    )
    patched = patched.replace(yield_anchor, yield_patch, 1)
    patched = patched.replace(
        '  printf "PHNIX post-parser pc=0x%x\\n", $pc\n',
        '  set $foxair_parser_injected = 0\n  printf "PHNIX post-parser pc=0x%x\\n", $pc\n',
        1,
    )
    # Breakpoint 4 is now the temporary parser system() guard.  Keep the
    # production script's later one-shot C357/C5A8 disables aligned with their
    # shifted QEMU-only breakpoint numbers.
    patched = patched.replace("    disable 4\n", "    disable 4004\n", 1)
    patched = patched.replace("    disable 5\n", "    disable 6\n", 1)
    patched = patched.replace("    disable 4004\n", "    disable 5\n", 1)
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
