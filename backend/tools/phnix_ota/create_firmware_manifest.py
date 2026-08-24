#!/usr/bin/env python3
"""Development-backend shim for the shared manifest tool."""

from pathlib import Path
import runpy

repo = Path(__file__).resolve().parents[3]
runpy.run_path(
    str(repo / "tools" / "phnix_ota" / "create_firmware_manifest.py"),
    run_name="__main__",
)
