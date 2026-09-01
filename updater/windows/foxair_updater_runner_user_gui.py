from __future__ import annotations

import re
import sys
from html import escape

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import foxair_updater_gui as base
import foxair_updater_runner_gui as runner


_FAILED_RUN_RE = re.compile(
    r"(?:/data/foxair_ota_runner/)?runs/([A-Za-z0-9._-]+)/payload/dtu_ota_supervisor\.sh"
)


class MainWindow(runner.MainWindow):
    """End-user presentation layer for the autonomous DTU runner GUI."""

    def _status(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        intro = QLabel(
            "Auf dieser Seite gibt es zwei getrennte Funktionen: den normalen "
            "<b>Originalzustand des LTE-Modems</b> und den Status eines "
            "<b>autonomen Firmwarelaufs</b>. Die Prüfung des Originalzustands ist read-only. "
            "Während eines laufenden Firmwareupdates darf der Originalzustand nicht erzwungen "
            "wiederhergestellt werden; dafür gibt es den sicheren Abbruch des laufenden Updates."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "QLabel{background:#f7f8fa;border:1px solid #d0d5dd;padding:9px;}"
        )
        layout.addWidget(intro)

        original_box = QGroupBox("LTE-Modem – Originalzustand")
        original_layout = QVBoxLayout(original_box)
        original_note = QLabel(
            "Prüft, ob der originale PHNIX-Dienst normal läuft und keine temporären "
            "Update-/Debugger-/Cloud-Sperrzustände aktiv sind. Die Prüfung verändert nichts. "
            "Die Wiederherstellung verwendet weiterhin den vorhandenen, abgesicherten "
            "Recoverypfad des bisherigen Controllers."
        )
        original_note.setWordWrap(True)
        original_layout.addWidget(original_note)

        row = QHBoxLayout()
        self.status_btn = QPushButton("Originalzustand prüfen (read-only)")
        self.status_btn.clicked.connect(self._original_status_run)
        row.addWidget(self.status_btn)
        self.original_restore_btn = QPushButton("Originalzustand wiederherstellen")
        self.original_restore_btn.clicked.connect(self._original_restore)
        row.addWidget(self.original_restore_btn)
        row.addStretch()
        original_layout.addLayout(row)

        # Keep this attribute for the established controller result renderer.
        self.status_text = QLabel("Originalzustand wurde noch nicht geprüft.")
        self.status_text.setWordWrap(True)
        self.status_text.setStyleSheet(
            "QLabel{background:#f7f8fa;border:1px solid #d0d5dd;padding:9px;}"
        )
        original_layout.addWidget(self.status_text)
        layout.addWidget(original_box)

        runner_box = QGroupBox("Autonomes Firmwareupdate – Laufstatus")
        runner_layout = QVBoxLayout(runner_box)
        runner_note = QLabel(
            "Nach dem Start läuft das Firmwareupdate auf dem LTE-Modem selbstständig weiter. "
            "Windows liest hier nur den gespeicherten Zustand. Ein sicherer Abbruch ist nur "
            "möglich, solange noch kein Firmwaretransfer zum Mainboard begonnen hat."
        )
        runner_note.setWordWrap(True)
        runner_layout.addWidget(runner_note)

        self.runner_status_text = QLabel("Noch kein Firmwarelauf gelesen.")
        self.runner_status_text.setWordWrap(True)
        self.runner_status_text.setStyleSheet(
            "QLabel{background:#f7f8fa;border:1px solid #d0d5dd;padding:9px;}"
        )
        runner_layout.addWidget(self.runner_status_text)

        row = QHBoxLayout()
        self.runner_status_btn = QPushButton("Firmwarelauf-Status lesen")
        self.runner_status_btn.clicked.connect(self._runner_status_run)
        row.addWidget(self.runner_status_btn)
        self.runner_log_btn = QPushButton("Technisches Laufprotokoll anzeigen")
        self.runner_log_btn.clicked.connect(self._runner_log)
        row.addWidget(self.runner_log_btn)
        row.addStretch()
        runner_layout.addLayout(row)

        self.runner_abort_btn = QPushButton("Update vor Firmwaretransfer sicher abbrechen")
        self.runner_abort_btn.clicked.connect(self._runner_abort)
        runner_layout.addWidget(self.runner_abort_btn)
        # Compatibility with the runner implementation, which controls the old
        # restore_btn attribute according to abort_allowed.
        self.restore_btn = self.runner_abort_btn

        row = QHBoxLayout()
        self.runner_ack_btn = QPushButton("Abgeschlossenes Ergebnis bestätigen")
        self.runner_ack_btn.setToolTip(
            "Bestätigt nur, dass das gespeicherte Endergebnis gesehen wurde. "
            "Es werden noch keine Diagnosedaten gelöscht."
        )
        self.runner_ack_btn.clicked.connect(self._runner_ack)
        row.addWidget(self.runner_ack_btn)
        self.runner_cleanup_btn = QPushButton("Bestätigte Laufdaten löschen")
        self.runner_cleanup_btn.setToolTip(
            "Löscht erst nach der Bestätigung die gespeicherten Daten dieses Firmwarelaufs "
            "vom LTE-Modem."
        )
        self.runner_cleanup_btn.clicked.connect(self._runner_cleanup)
        row.addWidget(self.runner_cleanup_btn)
        row.addStretch()
        runner_layout.addLayout(row)

        lifecycle = QLabel(
            "<b>Normaler Ablauf:</b> Paket prüfen → Firmwareupdate starten → LTE-Modem arbeitet "
            "autonom → Endergebnis wird gespeichert → Ergebnis bestätigen → Laufdaten bei Bedarf löschen."
        )
        lifecycle.setWordWrap(True)
        runner_layout.addWidget(lifecycle)
        layout.addWidget(runner_box)

        layout.addStretch()
        return widget

    def _original_status_run(self):
        base.MainWindow._status_run(self)

    def _original_restore(self):
        if self._runner_active:
            QMessageBox.warning(
                self,
                "Firmwareupdate läuft",
                "Während eines aktiven autonomen Firmwareupdates wird der Originalzustand nicht "
                "separat wiederhergestellt. Verwende dafür ausschließlich den sicheren Abbruch "
                "des Firmwarelaufs, solange dieser noch angeboten wird.",
            )
            return
        if (
            QMessageBox.question(
                self,
                "Originalzustand wiederherstellen",
                "Der vorhandene Recovery-Controller versucht, den normalen Originalbetrieb des "
                "LTE-Modems kontrolliert wiederherzustellen. Nach begonnenem Firmwaretransfer "
                "ist ein unsicherer Restore absichtlich gesperrt.\n\n"
                "Originalzustand jetzt wiederherstellen?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        ):
            self._backend("restore", ["run", "--restore", "original"])

    def _runner_status_run(self):
        if self._runner_run_id:
            self._run_runner("runner-status", "status", "--run-id", self._runner_run_id)
        else:
            self._run_runner("runner-current", "current")

    def _runner_abort(self):
        if not self._runner_run_id:
            QMessageBox.information(
                self,
                "Kein Firmwarelauf ausgewählt",
                "Lies zuerst den Firmwarelauf-Status, damit der laufende Vorgang eindeutig feststeht.",
            )
            return
        if not self._runner_abort_allowed:
            QMessageBox.warning(
                self,
                "Sicherer Abbruch nicht mehr möglich",
                "Der Firmwarelauf hat die sichere Abbruchgrenze bereits überschritten. "
                "Es wird kein erzwungener Restore ausgeführt.",
            )
            return
        if (
            QMessageBox.question(
                self,
                "Firmwareupdate sicher abbrechen",
                "Die Abbruchanforderung wird auf dem LTE-Modem gespeichert. Das LTE-Modem prüft "
                "selbst, ob der sichere Recoverypfad noch zulässig ist.\n\n"
                "Abbruch jetzt anfordern?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        ):
            self._run_runner("runner-abort", "abort-request", "--run-id", self._runner_run_id)

    # Keep the historic method names callable for inherited code, but route
    # visible buttons explicitly to the two separate actions above.
    def _status_run(self):
        self._original_status_run()

    def _restore(self):
        self._runner_abort()

    @staticmethod
    def _phase_text(phase: str) -> str:
        friendly = {
            "dry-run-complete": "Paket und LTE-Voraussetzungen vollständig geprüft",
            "local-preparation": "Firmwarelauf wird auf dem LTE-Modem vorbereitet",
            "service-restart": "PHNIX-Kommunikationsdienst wird kontrolliert neu gestartet",
            "staging": "Lokale Firmwaredatei wird geprüft",
            "hook-started": "Firmwarelauf wird gestartet",
            "hook-starting": "Firmwarelauf wird gestartet",
            "waiting-for-yield-loop": "LTE-Dienst wird für den sicheren Update-Start vorbereitet",
            "parser-injection": "Updateauftrag wird an den Originaldienst übergeben",
            "c350": "Update-Anfrage wurde an das Mainboard gesendet – Antwort wird erwartet",
            "c350-sent": "Update-Anfrage wurde an das Mainboard gesendet – Antwort wird erwartet",
            "accepted": "Mainboard hat das Firmwareupdate angenommen",
            "c357": "Firmwareübertragung wird vorbereitet",
            "c5a8": "Firmware wird an das Mainboard übertragen",
            "success-report": "Mainboard meldet Erfolg – Abschlussprüfung läuft",
            "success": "Firmwareupdate erfolgreich abgeschlossen",
            "same-version": "Gleiche Firmware erkannt – keine Übertragung erforderlich",
            "failed": "Firmwareupdate wurde mit einem Fehler beendet",
            "reboot-detected": "LTE-Modem wurde während eines laufenden Updates neu gestartet",
            "orphaned-run": "Gespeicherter Lauf ist nicht mehr aktiv",
            "package-preflight": "Vorprüfung des Updatepakets fehlgeschlagen",
        }
        return friendly.get(phase, runner.MainWindow._phase_text(phase))

    @staticmethod
    def _recovery_text(value: str) -> str:
        return {
            "not-required": "nicht erforderlich",
            "completed": "abgeschlossen",
            "required": "manuelle Prüfung erforderlich",
            "?": "noch nicht bestimmt",
        }.get(value, value or "noch nicht bestimmt")

    @staticmethod
    def _result_text(result: str, phase: str) -> str:
        value = result or phase
        return {
            "success": "erfolgreich abgeschlossen",
            "same-version": "gleiche Firmware – keine Übertragung",
            "aborted-before-transfer": "sicher vor Firmwaretransfer abgebrochen",
            "recovery-completed": "Recovery abgeschlossen",
            "failed": "mit Fehler beendet",
            "recovery-required": "manuelle Prüfung erforderlich",
            "reboot-detected": "durch Neustart unterbrochen",
            "orphaned": "nicht mehr aktiver Lauf erkannt",
        }.get(value, value or "noch offen")

    def _render_runner_status(self, status: dict) -> None:
        original_label = self.status_text
        self.status_text = self.runner_status_text
        try:
            super()._render_runner_status(status)
        finally:
            self.status_text = original_label

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
            + (f"<br><b>Mainboard-Schritt:</b> {board_step}" if isinstance(board_step, int) and board_step else "")
            + extra
            + (f"<br><br>{escape(detail)}" if detail else "")
            + (f"<br><small>Lauf-ID: <code>{escape(run_id)}</code></small>" if run_id else "")
        )
        if hasattr(self, "progress_sources"):
            text = f"Lauf-ID: {run_id or '?'} | {self._phase_text(phase)}"
            if isinstance(board_step, int) and board_step:
                text += f" | Mainboard-Schritt: {board_step}"
            self.progress_sources.setText(text)

    @staticmethod
    def _failed_run_id(output: str) -> str | None:
        match = _FAILED_RUN_RE.search(output)
        return match.group(1) if match else None

    @staticmethod
    def _friendly_failed_preflight(status: dict) -> str:
        reason = str(status.get("reason") or "")
        detail = str(status.get("detail") or "")
        transfer_started = status.get("transfer_started") is True
        if reason == "package_validation_failed" and "code 72" in detail.lower():
            text = (
                "Die Vorprüfung wurde abgelehnt, weil auf dem LTE-Modem noch ein bestehender "
                "OTA-/Hook-Zustand erkannt wurde."
            )
        elif reason == "package_validation_failed":
            text = "Die Vorprüfung des Updatepakets oder der LTE-Voraussetzungen ist fehlgeschlagen."
        else:
            text = detail or "Die Vorprüfung konnte nicht erfolgreich abgeschlossen werden."
        if not transfer_started:
            text += " Es wurde kein Firmwaretransfer zum Mainboard gestartet."
        return text

    def _done(self, op, code, output):
        if op == "runner-prepare":
            value = self._runner_json(output)
            if code != 0 or value is None or value.get("ok") is False:
                # Reuse the established process/log cleanup without the old
                # generic runner error popup; then read the failed run status.
                runner.legacy.MainWindow._done(self, "handled-result", code, output)
                self._runner_autostart_after_prepare = False
                self._runner_prepared_manifest = None
                run_id = self._failed_run_id(output)
                if run_id:
                    self._runner_run_id = run_id
                    self.runner_status_text.setText(
                        "Vorprüfung wurde abgelehnt – genauer Fehlerstatus wird vom LTE-Modem gelesen …"
                    )
                    QTimer.singleShot(
                        150,
                        lambda rid=run_id: self._run_runner(
                            "runner-failed-status", "status", "--run-id", rid
                        ),
                    )
                else:
                    error = value.get("error") if isinstance(value, dict) else ""
                    QMessageBox.critical(
                        self,
                        "Vorprüfung fehlgeschlagen",
                        "Die Vorprüfung konnte nicht abgeschlossen werden. Es wurde kein "
                        "Firmwareupdate gestartet. Details stehen im Protokoll."
                        + (f"\n\n{error}" if error else ""),
                    )
                return

        if op == "runner-failed-status":
            runner.legacy.MainWindow._done(self, "handled-result", code, output)
            status = self._runner_json(output)
            if code == 0 and isinstance(status, dict) and status.get("ok") is not False:
                failed_run = str(status.get("run_id") or "")
                if failed_run:
                    # A failed preflight is explained below with a dedicated,
                    # non-alarming message. Suppress the generic terminal popup.
                    self._runner_terminal_notified.add(failed_run)
                self._render_runner_status(status)
                QMessageBox.warning(
                    self,
                    "Vorprüfung abgelehnt",
                    self._friendly_failed_preflight(status),
                )
            else:
                QMessageBox.warning(
                    self,
                    "Vorprüfung fehlgeschlagen",
                    "Die Vorprüfung wurde abgelehnt; der zugehörige Detailstatus konnte nicht "
                    "automatisch gelesen werden. Es wurde kein Firmwareupdate gestartet. "
                    "Details stehen im Protokoll.",
                )
            return

        if op.startswith("runner-"):
            original_label = self.status_text
            self.status_text = self.runner_status_text
            try:
                super()._done(op, code, output)
            finally:
                self.status_text = original_label
            return

        super()._done(op, code, output)

    def _buttons(self):
        super()._buttons()
        if not hasattr(self, "runner_status_btn"):
            return
        enabled = not self.busy
        adb_ready = self._adb_ready()
        self.status_btn.setEnabled(enabled and adb_ready)
        self.original_restore_btn.setEnabled(enabled and adb_ready and not self._runner_active)
        self.runner_status_btn.setEnabled(enabled and adb_ready)
        self.runner_log_btn.setEnabled(enabled and adb_ready)
        self.runner_abort_btn.setEnabled(enabled and adb_ready and self._runner_abort_allowed)
        self.runner_ack_btn.setEnabled(enabled and adb_ready and self._runner_terminal)
        self.runner_cleanup_btn.setEnabled(
            enabled and adb_ready and self._runner_terminal and self._runner_acknowledged
        )


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
