#!/usr/bin/env python3
"""Development-backend entry point matching the packaged Windows route."""

from pathlib import Path
import runpy

repo = Path(__file__).resolve().parents[3]
runpy.run_path(
    str(repo / "updater" / "windows" / "phnix_windows_controller_wrapper.py"),
    run_name="__main__",
)
