from __future__ import annotations

import sys
from datetime import datetime
from html import escape
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import foxair_updater_gui as base
import foxair_updater_runner_user_gui as user_gui


class MainWindow(user_gui.MainWindow):
    """Final end-user presentation for the autonomous DTU runner.

    This layer deliberately does not change runner decisions.  It restores the
    proven Windows presentation features from the previous controller GUI:
    automatic controller/LTE logs beside the firmware, dual progress sources,
    source fallback and a more detailed visible phase history.
    """

    def __init__(self):
        self._runner_log_run_id: str | None = None
        self._runner_progress_value: int | None = None
        self._runner_progress_offset: int | None = None
        self._runner_progress_length: int | None = None
        self._runner_transfer_visible = False
        super().__init__()
        self.update_btn.setText("Firmwareupdate starten")
        self._log(f"[FoxAir Updater] Version {base.APP_VERSION} – autonomer DTU-Runner")

    # ------------------------------------------------------------------
    # Automatic update logs
    # ------------------------------------------------------------------
    def _log(self, text):
        """Keep the on-screen protocol unchanged, but timestamp every automatic log line."""
        automatic_log = getattr(self, "_automatic_log", None)
        if automatic_log is None:
            super()._log(text)
            return

        # The inherited implementation also writes to _automatic_log. Temporarily
        # hide that stream so the GUI protocol is still handled normally without
        # duplicating the file entry, then write the timestamped file line here.
        self._automatic_log = None
        try:
            super()._log(text)
        finally:
            self._automatic_log = automatic_log

        try:
            lines = str(text).splitlines() or [""]
            for line in lines:
                stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                automatic_log.write(f"[{stamp}] {line}\n")
            automatic_log.flush()
        except OSError as error:
            self._automatic_log = None
            super()._log(
                f"[Warnung] Automatisches Controller-Log konnte nicht weitergeschrieben werden: {error}"
            )

    def _run_runner(self, op: str, *args: str) -> None:
        # Use exactly the established automatic logging implementation from the
        # previous GUI.  It creates:
        #   <firmware-dir>/Logs/FoxAir_Update_<timestamp>.log
        #   <firmware-dir>/Logs/FoxAir_Update_<timestamp>_LTE.log
        # and falls back to the firmware directory only if Logs cannot be used.
        if op == "runner-prepare":
            manifest = None
            try:
                index = args.index("--manifest")
                candidate = Path(args[index + 1])
                if candidate.is_file():
                    manifest = candidate
            except (ValueError, IndexError, TypeError):
                pass
            if manifest is not None:
                self._start_automatic_logs(manifest)
                self._runner_log_run_id = None
                self._runner_progress_value = None
                self._runner_progress_offset = None
                self._runner_progress_length = None
                self._runner_transfer_visible = False
                # Header goes into the on-screen protocol and, because the
                # established automatic log is already open, into that file too.
                self._log(
                    f"[FoxAir Updater] Version {base.APP_VERSION} – autonomer DTU-Runner"
                )
                self._log(f"[Update-Log] Firmware-Verzeichnis: {manifest.parent}")
        super()._run_runner(op, *args)

    def _log_runner_id_once(self, run_id: str) -> None:
        if not run_id or run_id == self._runner_log_run_id:
            return
        self._runner_log_run_id = run_id
        self._log(f"[DTU Runner] Lauf-ID: {run_id}")

    # ------------------------------------------------------------------
    # User-facing phases / flow history
    # ------------------------------------------------------------------
    @staticmethod
    def _phase_text(phase: str) -> str:
        friendly = {
            "attaching": "Update-Überwachung wird mit dem LTE-Dienst verbunden",
            "hook-ended-before-authority": (
                "Update-Überwachung vor Beginn beendet – Originalzustand wiederhergestellt"
            ),
            "original-service-active-unmonitored": (
                "Originaldienst führt das Update weiter – lokale Überwachung wurde beendet"
            ),
            "post-restart-preflight": "LTE-Dienst wird nach dem Neustart erneut geprüft",
            "local-http": "Firmwaredatei wird lokal für das LTE-Modem bereitgestellt",
            "invalid-success-boundary": "Mainboard-Abschluss konnte noch nicht sicher bestätigt werden",
            "invalid-failure-boundary": "Mainboard-Fehlerabschluss konnte noch nicht sicher bestätigt werden",
        }
        return friendly.get(phase, user_gui.MainWindow._phase_text(phase))

    def _update_flow_from_runner(self, status: dict) -> None:
        phase = str(status.get("phase") or "")
        terminal = status.get("terminal") is True
        result_type = str(status.get("result_type") or "")
        transfer_started = status.get("transfer_started") is True

        phase_steps = {
            "dry-run-complete": (
                "runner-preflight-user", "ok",
                "Paket, Firmwaredatei, Hashes, Speicher und LTE-Voraussetzungen geprüft.",
            ),
            "local-preparation": (
                "runner-local-preparation", "ok",
                "Autonomer Firmwarelauf wurde auf dem LTE-Modem übernommen.",
            ),
            "service-restart": (
                "runner-service-restart", "warn",
                "PHNIX-Kommunikationsdienst wird kontrolliert neu gestartet.",
            ),
            "staging": (
                "runner-staging", "ok",
                "Firmwaredatei wird lokal bereitgestellt und verifiziert.",
            ),
            "hook-started": (
                "runner-monitor", "ok",
                "Update-Überwachung auf dem LTE-Modem wurde gestartet.",
            ),
            "hook-starting": (
                "runner-monitor", "warn",
                "Update-Überwachung auf dem LTE-Modem wird gestartet.",
            ),
            "attaching": (
                "runner-monitor", "warn",
                "Update-Überwachung verbindet sich mit dem laufenden PHNIX-Dienst.",
            ),
            "waiting-for-yield-loop": (
                "runner-yield", "warn",
                "Sicherer Startpunkt im PHNIX-Originaldienst wird abgewartet.",
            ),
            "parser-injection": (
                "runner-parser", "warn",
                "Firmwareauftrag wird kontrolliert an den PHNIX-Originaldienst übergeben.",
            ),
            "c350": (
                "runner-c350-user", "warn",
                "Firmwareangebot wurde an das Mainboard gesendet; Antwort wird ausgewertet.",
            ),
            "c350-sent": (
                "runner-c350-user", "warn",
                "Firmwareangebot wurde an das Mainboard gesendet; Antwort wird ausgewertet.",
            ),
            "accepted": (
                "runner-accepted-user", "ok",
                "Mainboard hat das Firmwareupdate angenommen.",
            ),
            "c357": (
                "runner-c357-user", "ok",
                "Mainboard hat die Transfermetadaten angenommen.",
            ),
            "c5a8": (
                "phase-c5a8", "warn",
                "Firmwaredaten werden an das Mainboard übertragen.",
            ),
            "success-report": (
                "runner-success-report", "ok",
                "Mainboard meldet den Transferabschluss; Abschlussgrenze wird geprüft.",
            ),
            "same-version": (
                "runner-same-user", "ok",
                "Gleiche Firmware erkannt; es wurden keine Firmwaredaten übertragen.",
            ),
            "hook-ended-before-authority": (
                "runner-recovery-user", "warn",
                "Überwachung endete vor dem Firmwaretransfer; Originalzustand wurde wiederhergestellt.",
            ),
        }
        item = phase_steps.get(phase)
        if item:
            self._set_step(*item)

        if transfer_started and "phase-c5a8" not in self._flow_steps:
            self._set_step(
                "phase-c5a8", "warn",
                "Firmwaredaten werden an das Mainboard übertragen.",
            )

        if terminal:
            if result_type == "success":
                self._set_step(
                    "runner-terminal-user", "ok",
                    "Firmwareupdate und Mainboard-Abschluss wurden terminal bestätigt.",
                )
            elif result_type == "same-version":
                self._set_step(
                    "runner-terminal-user", "ok",
                    "Gleiche Firmware sicher erkannt; kein Firmwaretransfer erforderlich.",
                )
            elif result_type == "recovery-completed":
                self._set_step(
                    "runner-terminal-user", "warn",
                    "Sicherer Pre-Transfer-Recoverypfad wurde abgeschlossen.",
                )
            elif result_type == "aborted-before-transfer":
                self._set_step(
                    "runner-terminal-user", "warn",
                    "Firmwarelauf wurde sicher vor Beginn des Transfers abgebrochen.",
                )

    # ------------------------------------------------------------------
    # Dual transfer progress: serial PHNIX log + autonomous runner
    # ------------------------------------------------------------------
    def _render_transfer_progress(self) -> None:
        """Restore the previous dual-source progress behavior.

        PHNIX serial progress is preferred for the bar while it is available.
        If that source disappears, the inherited debug status handling clears
        ``_phnix_transfer_event`` and the runner value automatically becomes the
        displayed fallback.  Both values are listed below the bar whenever both
        are available.
        """
        event = self._phnix_transfer_event
        runner_percent = self._runner_progress_value
        runner_offset = self._runner_progress_offset
        runner_length = self._runner_progress_length

        lines: list[str] = []
        display_percent: float | int | None = None

        if event is not None:
            serial_percent = float(event.progress)
            display_percent = serial_percent
            lines.append(
                (
                    f"PHNIX Originaldienst: {serial_percent:.1f} % · "
                    f"{event.current:,} / {event.total:,} Byte"
                ).replace(",", ".")
            )

        if runner_percent is not None and self._runner_transfer_visible:
            if display_percent is None:
                display_percent = runner_percent
            if (
                isinstance(runner_offset, int)
                and isinstance(runner_length, int)
                and runner_length > 0
            ):
                lines.append(
                    (
                        f"DTU-Runner: {runner_percent} % · "
                        f"{runner_offset:,} / {runner_length:,} Byte"
                    ).replace(",", ".")
                )
            else:
                lines.append(f"DTU-Runner: {runner_percent} %")

        if display_percent is not None:
            value = max(0, min(100, round(display_percent)))
            self.progress.setValue(value)
            # No text inside the bar.  The existing large percent label remains
            # next to it; detailed values stay below the bar.
            self.progress.setFormat("")
            if hasattr(self, "progress_percent_label"):
                if event is not None:
                    self.progress_percent_label.setText(f"{float(display_percent):.1f} %")
                else:
                    self.progress_percent_label.setText(f"{value} %")
        else:
            self.progress.setValue(0)
            self.progress.setFormat("")
            if hasattr(self, "progress_percent_label"):
                self.progress_percent_label.setText("–")

        if hasattr(self, "progress_sources"):
            self.progress_sources.setText("\n".join(lines))

    def _render_runner_status(self, status: dict) -> None:
        # Let the established runner layer update all lifecycle/safety state,
        # buttons and terminal dialogs first.
        super()._render_runner_status(status)

        run_id = str(status.get("run_id") or "")
        state = str(status.get("state") or "?")
        phase = str(status.get("phase") or "?")
        result_type = str(status.get("result_type") or "")
        terminal = status.get("terminal") is True
        transfer_started = status.get("transfer_started") is True
        authoritative = status.get("original_service_authoritative") is True
        recovery = str(status.get("recovery") or "?")
        detail = str(status.get("detail") or "")
        board_step = status.get("board_ota_step")
        progress = status.get("progress")
        offset = status.get("offset")
        length = status.get("length")

        self._log_runner_id_once(run_id)
        self._update_flow_from_runner(status)

        if isinstance(progress, int):
            self._runner_progress_value = max(0, min(100, progress))
        if isinstance(offset, int):
            self._runner_progress_offset = offset
        if isinstance(length, int):
            self._runner_progress_length = length
        self._runner_transfer_visible = bool(
            transfer_started
            or phase == "c5a8"
            or (isinstance(length, int) and length > 0)
        )

        if self._runner_transfer_visible:
            self._render_transfer_progress()
        else:
            # Before C5A8 there is no meaningful percentage.  Same-version and
            # recovery runs therefore no longer show a misleading "0 % DTU Runner".
            self.progress.setValue(0)
            self.progress.setFormat("")
            if hasattr(self, "progress_percent_label"):
                self.progress_percent_label.setText("–")
            if hasattr(self, "progress_sources"):
                phase_line = self._phase_text(phase)
                if isinstance(board_step, int) and board_step:
                    phase_line += f" · Mainboard-Schritt {board_step}"
                self.progress_sources.setText(phase_line)

        # Re-render the status box without the technical run ID.  The run ID is
        # written once to the protocol/automatic log instead.
        if terminal:
            headline = f"<b>Abgeschlossen:</b> {escape(self._result_text(result_type, phase))}"
        elif state == "prepared":
            headline = "<b>Bereit:</b> Paket ist geprüft; Firmwareupdate wurde noch nicht gestartet."
        elif state == "running":
            headline = "<b>Firmwareupdate läuft auf dem LTE-Modem.</b>"
        else:
            headline = f"<b>Zustand:</b> {escape(state)}"

        abort_text = "möglich" if self._runner_abort_allowed else "nicht möglich"
        transfer_text = "gestartet" if transfer_started else "noch nicht gestartet"
        extra = ""
        if authoritative:
            extra = (
                "<br><b>Hinweis:</b> Der originale PHNIX-Dienst führt das Update jetzt selbst weiter; "
                "ein sicherer Abbruch ist ab dieser Grenze gesperrt."
            )
        self.runner_status_text.setText(
            headline
            + f"<br><b>Aktueller Schritt:</b> {escape(self._phase_text(phase))}"
            + f"<br><b>Firmwareübertragung:</b> {transfer_text}"
            + f"<br><b>Sicherer Abbruch:</b> {abort_text}"
            + f"<br><b>Recovery:</b> {escape(self._recovery_text(recovery))}"
            + (
                f"<br><b>Mainboard-Schritt:</b> {board_step}"
                if isinstance(board_step, int) and board_step
                else ""
            )
            + extra
            + (f"<br><br>{escape(detail)}" if detail else "")
        )

        if terminal:
            # Final runner JSON has already passed through _line() and therefore
            # reached the automatic controller log.  It is now safe to close
            # both established automatic log streams.
            QTimer.singleShot(0, self._finish_automatic_logs)

    def _done(self, op, code, output):
        super()._done(op, code, output)
        if op == "runner-prepare" and code != 0 and not self._runner_run_id:
            self._finish_automatic_logs()


def main():
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
