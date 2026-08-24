#!/usr/bin/env python3
"""Source-mode shim to the shared host safety layer."""

from pathlib import Path
import runpy

repo = Path(__file__).resolve().parents[2]
runpy.run_path(
    str(repo / "tools" / "phnix_ota" / "phnix_local_ota_controller_hardened.py"),
    run_name="__main__",
)
