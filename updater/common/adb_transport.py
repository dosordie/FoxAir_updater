"""Cross-platform subprocess transport for Android Debug Bridge.

The implementation deliberately contains no Linux-only path discovery.  A
Windows frontend can pass the path to a separately installed ``adb.exe`` while
the Linux/Raspberry-Pi launcher passes ``adb`` or the VM simulator shim.

``env`` is optional and primarily used by the Windows GUI for remote ADB via
``ADB_SERVER_SOCKET``.  Keeping it in the transport avoids duplicating process
invocation code in read-only diagnostic helpers.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


class TransportError(RuntimeError):
    """The selected device transport failed."""


class AdbClient:
    def __init__(
        self,
        executable: str | Path,
        serial: str | None = None,
        env: dict[str, str] | None = None,
    ):
        self.base = [str(executable)]
        if serial:
            self.base += ["-s", serial]
        self.env = dict(env) if env is not None else None

    @staticmethod
    def _creationflags() -> int:
        # A windowed PyInstaller application otherwise causes adb.exe (and on
        # some systems its shell helper) to flash a console window for every
        # short diagnostic command.
        if os.name == "nt":
            return getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return 0

    def run(self, *args: str, binary: bool = False, check: bool = True):
        completed = subprocess.run(
            [*self.base, *args],
            capture_output=True,
            text=not binary,
            check=False,
            env=self.env,
            creationflags=self._creationflags(),
        )
        if check and completed.returncode != 0:
            stderr = completed.stderr
            if binary:
                stderr = stderr.decode(errors="replace")
            raise TransportError(f"adb {' '.join(args)} failed: {stderr.strip()}")
        return completed.stdout

    def shell(self, command: str, check: bool = True) -> str:
        return self.run("shell", command, check=check).strip()

    def read_file(self, remote: str) -> bytes:
        # The older modem adbd closes exec-out. shell/cat preserves the binary
        # stream on Linux and Windows hosts as long as subprocess uses bytes.
        return self.run("shell", "cat", remote, binary=True)

    def push(self, local: str | Path, remote: str) -> None:
        self.run("push", str(local), remote)

    def popen_shell(self, command: str) -> subprocess.Popen:
        env = self.env if self.env is not None else os.environ.copy()
        return subprocess.Popen(
            [*self.base, "shell", command],
            env=env,
            creationflags=self._creationflags(),
        )
