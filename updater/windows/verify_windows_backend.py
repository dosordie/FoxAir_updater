from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from prepare_legacy_restore_hook import LEGACY_HEADER, legacy_hook_bytes


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_equal(source: Path, copied: Path) -> None:
    if not copied.is_file():
        raise RuntimeError(f"Backend-Datei fehlt: {copied}")
    if sha256(source) != sha256(copied):
        raise RuntimeError(f"Backend-Datei weicht ab: {source} -> {copied}")


def verify(root: Path, out: Path) -> None:
    pairs = [
        (root / "tools/phnix_ota/phnix_local_ota_controller.py", out / "backend/tools/phnix_ota/phnix_local_ota_controller_core.py"),
        (root / "tools/phnix_ota/phnix_local_ota_controller_hardened.py", out / "backend/tools/phnix_ota/phnix_local_ota_controller_hardened.py"),
        (root / "updater/windows/phnix_windows_controller_wrapper.py", out / "backend/tools/phnix_ota/phnix_local_ota_controller.py"),
        (root / "tools/phnix_ota/create_firmware_manifest.py", out / "backend/tools/phnix_ota/create_firmware_manifest.py"),
        (root / "tools/phnix_traffic/foxair_traffic_trace", out / "backend/tools/phnix_traffic/foxair_traffic_trace"),
        (root / "updater/dtu_ota/payload/dtu_ota_supervisor.sh", out / "backend/updater/dtu_ota/payload/dtu_ota_supervisor.sh"),
        (root / "updater/dtu_ota/payload/phnix_ota_runtime_hook", out / "backend/updater/dtu_ota/payload/phnix_ota_runtime_hook"),
    ]
    pairs.extend(
        (path, out / "backend/updater/dtu_ota" / path.name)
        for path in sorted((root / "updater/dtu_ota").glob("*.py"))
    )
    pairs.extend(
        (path, out / "backend/updater/common" / path.name)
        for path in sorted((root / "updater/common").glob("*.py"))
    )
    for source, copied in pairs:
        require_equal(source, copied)

    legacy = out / "backend/tools/phnix_ota/phnix_ota_runtime_hook"
    if not legacy.is_file():
        raise RuntimeError(f"Legacy-Restore-Hook fehlt: {legacy}")

    canonical = root / "updater/dtu_ota/payload/phnix_ota_runtime_hook"
    expected_legacy = legacy_hook_bytes(canonical.read_bytes())
    legacy_raw = legacy.read_bytes()
    if legacy_raw != expected_legacy:
        raise RuntimeError(
            "Legacy-Restore-Hook entspricht nicht der LF-normalisierten kanonischen Quelle"
        )
    if not legacy_raw.startswith(LEGACY_HEADER):
        raise RuntimeError("Legacy-Restore-Hook hat keinen exakten LF-Header #!/bin/sh")
    if b"\r" in legacy_raw:
        raise RuntimeError("Legacy-Restore-Hook enthält weiterhin CR-Zeilenenden")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    verify(args.root.resolve(), args.out.resolve())
    print("[OK] Gemeinsamer Controller/Common-Code und produktiver DTU-Runner wurden inhaltlich verifiziert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
