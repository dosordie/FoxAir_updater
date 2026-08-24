#!/usr/bin/env python3
"""Source-mode shim to the shared manifest implementation."""

from pathlib import Path
import runpy

repo = Path(__file__).resolve().parents[2]
runpy.run_path(
    str(repo / "tools" / "phnix_ota" / "create_firmware_manifest.py"),
    run_name="__main__",
)
