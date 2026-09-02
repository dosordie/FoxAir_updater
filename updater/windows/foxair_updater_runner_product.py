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
    FLOW_KEY_ALIASES = {
        # The lower runner layer already creates these rows. Re-use those keys
        # so the end-user wording updates the existing row instead of adding an
        # identical second bullet.
        "runner-preflight-user": "runner-preflight",
        "runner-terminal-user": "runner-terminal",
    }

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

    def _set_step(self, key: str, level: str, text: str):
        """Collapse presentation aliases onto the existing runner flow row."""
        return super()._set_step(self.FLOW_KEY_ALIASES.get(key, key), level, text)

    def _render_runner_status(self, status: dict) -> None:
        """Apply final product-only presentation cleanup after runner rendering."""
        super()._render_runner_status(status)

        phase = str(status.get("phase") or "")
        if phase == "dry-run-complete" and not self._runner_autostart_after_prepare:
            # The completed preflight is already fully represented in the flow
            # box. Do not repeat the same state directly below it as a large
            # progress caption/source line when no transfer exists yet.
            self._flow_title = "Vorprüfung erfolgreich"
            self.progress_text.clear()
            if hasattr(self, "progress_sources"):
                self.progress_sources.clear()
            self._render_flow()

        if (
            status.get("service_restart_requested") is True
            and status.get("service_restart_verified") is True
        ):
            self._set_step(
                "runner-service-restart",
                "ok",
                "LTE-Kommunikationsdienst wurde kontrolliert neu gestartet.",
            )

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
