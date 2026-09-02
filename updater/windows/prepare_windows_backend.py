from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from prepare_legacy_restore_hook import prepare as prepare_legacy_hook
from verify_windows_backend import verify


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def prepare_backend(root: Path, out: Path) -> None:
    backend = out / "backend"
    if backend.exists():
        shutil.rmtree(backend)

    copy_file(root / "updater/__init__.py", backend / "updater/__init__.py")

    for source in sorted((root / "updater/common").glob("*.py")):
        copy_file(source, backend / "updater/common" / source.name)

    copy_file(
        root / "tools/phnix_ota/phnix_local_ota_controller.py",
        backend / "tools/phnix_ota/phnix_local_ota_controller_core.py",
    )
    copy_file(
        root / "tools/phnix_ota/phnix_local_ota_controller_hardened.py",
        backend / "tools/phnix_ota/phnix_local_ota_controller_hardened.py",
    )
    copy_file(
        root / "updater/windows/phnix_windows_controller_wrapper.py",
        backend / "tools/phnix_ota/phnix_local_ota_controller.py",
    )
    copy_file(
        root / "tools/phnix_ota/create_firmware_manifest.py",
        backend / "tools/phnix_ota/create_firmware_manifest.py",
    )
    # The legacy controller validates the local helper before doing even a
    # restore.  Windows worktrees can still contain CRLF despite .gitattributes,
    # so both packaged helper locations must contain deterministic Unix LF.
    prepare_legacy_hook(
        root / "updater/dtu_ota/payload/phnix_ota_runtime_hook",
        backend / "tools/phnix_ota/phnix_ota_runtime_hook",
    )
    copy_file(
        root / "tools/phnix_traffic/foxair_traffic_trace",
        backend / "tools/phnix_traffic/foxair_traffic_trace",
    )

    for source in sorted((root / "updater/dtu_ota").glob("*.py")):
        copy_file(source, backend / "updater/dtu_ota" / source.name)
    copy_file(
        root / "updater/dtu_ota/payload/dtu_ota_supervisor.sh",
        backend / "updater/dtu_ota/payload/dtu_ota_supervisor.sh",
    )
    prepare_legacy_hook(
        root / "updater/dtu_ota/payload/phnix_ota_runtime_hook",
        backend / "updater/dtu_ota/payload/phnix_ota_runtime_hook",
    )

    verify(root, out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.out.resolve()
    prepare_backend(root, out)
    print("[OK] Windows-Backend vorbereitet und inhaltlich verifiziert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
