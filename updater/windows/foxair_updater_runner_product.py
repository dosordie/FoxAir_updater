from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import foxair_updater_gui as base
import foxair_updater_runner_enduser as enduser


class MainWindow(enduser.MainWindow):
    """Final Windows product glue for the autonomous DTU runner.

    Keeps release-specific path wiring and serial-progress fallback out of the
    generic runner layers. The actual OTA decisions stay in the DTU runner.
    """

    SERIAL_PROGRESS_STALE_SECONDS = 15.0

    def __init__(self):
        self._serial_progress_seen_at: float | None = None
        super().__init__()
        self._serial_progress_watchdog = QTimer(self)
        self._serial_progress_watchdog.setInterval(5000)
        self._serial_progress_watchdog.timeout.connect(self._expire_stale_serial_progress)
        self._serial_progress_watchdog.start()

    def _runner_cli(self) -> Path:
        """Use the production runner package after the repository relocation."""
        return base.backend_dir() / "updater/dtu_ota/cli.py"

    def _update_debug_line(self, line: str, event: object) -> None:
        """Accept live serial transfer progress for autonomous runner updates.

        The inherited diagnostics layer only accepts serial progress after the
        legacy controller created a ``phase-c5a8`` row. Autonomous runner runs
        use ``runner-c5a8`` instead, so otherwise the LTE log is written but the
        visible serial percentage never updates.
        """
        super()._update_debug_line(line, event)
        if (
            getattr(event, "kind", None) == "transfer-progress"
            and self._runner_run_id
            and not self._runner_terminal
        ):
            # A live transfer-progress event itself is sufficient evidence for
            # the presentation layer that a percentage is meaningful. This also
            # prevents a runner poll that is a fraction behind from resetting
            # the freshly received serial percentage back to an empty bar.
            self._runner_transfer_visible = True
            self._phnix_transfer_event = event
            self._serial_progress_seen_at = time.monotonic()
            self._render_transfer_progress()

    def _debug_status(self, status: str, error: object) -> None:
        super()._debug_status(status, error)
        if status in {"Getrennt", "Verbindung beendet", "Verbindung fehlgeschlagen"}:
            self._serial_progress_seen_at = None

    def _expire_stale_serial_progress(self) -> None:
        """Fall back to runner progress if a connected serial stream goes stale."""
        if (
            self._phnix_transfer_event is None
            or self._serial_progress_seen_at is None
            or self._runner_terminal
        ):
            return
        if time.monotonic() - self._serial_progress_seen_at < self.SERIAL_PROGRESS_STALE_SECONDS:
            return
        self._phnix_transfer_event = None
        self._serial_progress_seen_at = None
        if self._runner_transfer_visible:
            self._render_transfer_progress()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("FoxAir Updater")
    app.setOrganizationName("FoxAir")
    icon = base.root_dir() / "app_icon.ico"
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
