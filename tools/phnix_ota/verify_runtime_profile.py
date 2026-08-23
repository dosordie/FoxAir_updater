#!/usr/bin/env python3
"""Verify that the analyzed service matches every cancel breakpoint opcode."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for candidate in (Path(__file__).resolve().parents[2], Path.cwd()):
    if (candidate / "updater/common/runtime_profile.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from updater.common.runtime_profile import verify_runtime_binary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("service", type=Path)
    result = verify_runtime_binary(parser.parse_args().service)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
