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
            "Auf dieser Seite kannst du den normalen <b>Originalzustand des LTE-Modems</b> "
            "prüfen und den gespeicherten Status eines <b>Firmwareupdates</b> anzeigen. "
            "Die Statusprüfung verändert nichts. Während eines laufenden Firmwareupdates darf "
            "der Originalzustand nicht erzwungen wiederhergestellt werden."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "QLabel{background:#f7f8fa;border:1px solid #d0d5dd;padding:9px;}"
        )
        layout.addWidget(intro)

        original_box = QGroupBox("LTE-Modem – Originalzustand")
        original_layout = QVBoxLayout(original_box)
        original_note = QLabel(
            "Prüft, ob das LTE-Modem wieder im normalen Betriebszustand ist und keine "
            "temporären Updatezustände mehr aktiv sind. Die Prüfung verändert nichts. "
            "Falls nötig, kann der ursprüngliche Betriebszustand kontrolliert wiederhergestellt werden."
        )
        original_note.setWordWrap(True)
        original_layout.addWidget(original_note)

        row = QHBoxLayout()
        self.status_btn = QPushButton("Originalzustand prüfen")
        self.status_btn.setToolTip("Nur Prüfung – es werden keine Einstellungen oder Dateien verändert.")
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

        runner_box = QGroupBox("Firmwareupdate – gespeicherter Status")
        runner_layout = QVBoxLayout(runner_box)
        runner_note = QLabel(
            "Nach dem Start läuft das Firmwareupdate auf dem LTE-Modem selbstständig weiter. "
            "Windows liest hier nur den gespeicherten Zustand. Ein sicherer Abbruch ist nur "
            "möglich, solange noch keine Firmwaredaten an das Mainboard übertragen werden."
        )
        runner_note.setWordWrap(True)
        runner_layout.addWidget(runner_note)

        self.runner_status_text = QLabel("Noch kein Update-Status gelesen.")
        self.runner_status_text.setWordWrap(True)
        self.runner_status_text.setStyleSheet(
            "QLabel{background:#f7f8fa;border:1px solid #d0d5dd;padding:9px;}"
        )
        runner_layout.addWidget(self.runner_status_text)

        row = QHBoxLayout()
        self.runner_status_btn = QPushButton("Update-Status lesen")
        self.runner_status_btn.clicked.connect(self._runner_status_run)
        row.addWidget(self.runner_status_btn)
        self.runner_log_btn = QPushButton("Technisches Laufprotokoll anzeigen")
        self.runner_log_btn.clicked.connect(self._runner_log)
        row.addWidget(self.runner_log_btn)
        row.addStretch()
        runner_layout.addLayout(row)

        self.runner_abort_btn = QPushButton("Firmwareupdate sicher abbrechen")
        self.runner_abort_btn.setToolTip(
            "Nur möglich, solange die Firmwareübertragung zum Mainboard noch nicht begonnen hat."
        )
        self.runner_abort_btn.clicked.connect(self._runner_abort)
        runner_layout.addWidget(self.runner_abort_btn)
        # Compatibility with the runner implementation, which controls the old
        # restore_btn attribute according to abort_allowed.
        self.restore_btn = self.runner_abort_btn

        row = QHBoxLayout()
        self.runner_ack_btn = QPushButton("Abgeschlossenes Ergebnis bestätigen")
        self.runner_ack_btn.setToolTip(
            "Bestätigt nur, dass das gespeicherte Endergebnis gesehen wurde. "
            "Diagnosedaten werden dabei noch nicht gelöscht."
        )
        self.runner_ack_btn.clicked.connect(self._runner_ack)
        row.addWidget(self.runner_ack_btn)
        self.runner_cleanup_btn = QPushButton("Gespeicherte Updatedaten löschen")
        self.runner_cleanup_btn.setToolTip(
            "Löscht nach der Bestätigung die gespeicherten Daten dieses Firmwareupdates vom LTE-Modem."
        )
        self.runner_cleanup_btn.clicked.connect(self._runner_cleanup)
        row.addWidget(self.runner_cleanup_btn)
        row.addStretch()
        runner_layout.addLayout(row)

        lifecycle = QLabel(
            "<b>Normaler Ablauf:</b> Vorprüfung → Firmwareupdate starten → LTE-Modem arbeitet "
            "selbstständig weiter → Endergebnis wird gespeichert → Ergebnis bestätigen → "
            "gespeicherte Updatedaten bei Bedarf löschen."
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
                "Während eines laufenden Firmwareupdates wird der Originalzustand nicht separat "
                "wiederhergestellt. Verwende dafür nur den sicheren Abbruch, solange dieser noch möglich ist.",
            )
            return
        if (
            QMessageBox.question(
                self,
                "Originalzustand wiederherstellen",
                "Das LTE-Modem versucht, den normalen Originalbetrieb kontrolliert "
                "wiederherzustellen. Nach Beginn der Firmwareübertragung ist diese Funktion "
                "aus Sicherheitsgründen gesperrt.\n\n"
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
                "Kein Firmwareupdate ausgewählt",
                "Lies zuerst den Update-Status, damit der laufende Vorgang eindeutig feststeht.",
            )
            return
        if not self._runner_abort_allowed:
            QMessageBox.warning(
                self,
                "Sicherer Abbruch nicht mehr möglich",
                "Die sichere Abbruchgrenze wurde bereits überschritten. Das Firmwareupdate wird "
                "deshalb nicht erzwungen abgebrochen.",
            )
            return
        if (
            QMessageBox.question(
                self,
                "Firmwareupdate sicher abbrechen",
                "Die Abbruchanforderung wird auf dem LTE-Modem gespeichert. Das LTE-Modem prüft "
                "selbst, ob der Vorgang noch sicher beendet und der Originalzustand "
                "wiederhergestellt werden kann.\n\n"
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
            "dry-run-complete": "Update-Datei und LTE-Modem vollständig geprüft",
            "local-preparation": "Firmwareupdate wird auf dem LTE-Modem vorbereitet",
            "service-restart": "LTE-Kommunikationsdienst wird für das Update neu gestartet",
            "staging": "Firmwaredatei wird für das Update geprüft",
            "hook-started": "Update-Überwachung wurde gestartet",
            "hook-starting": "Update-Überwachung wird gestartet",
            "waiting-for-yield-loop": "Sicherer Start des Firmwareupdates wird vorbereitet",
            "parser-injection": "Firmwareupdate wird an das Mainboard übergeben",
            "c350": "Update-Anfrage wurde an das Mainboard gesendet – Antwort wird erwartet",
            "c350-sent": "Update-Anfrage wurde an das Mainboard gesendet – Antwort wird erwartet",
            "accepted": "Mainboard hat das Firmwareupdate angenommen",
            "c357": "Firmwareübertragung wird vorbereitet",
            "c5a8": "Firmware wird an das Mainboard übertragen",
            "success-report": "Firmware vollständig übertragen – Abschlussprüfung läuft",
            "success": "Firmwareupdate erfolgreich abgeschlossen",
            "same-version": "Gleiche Firmware erkannt – keine Übertragung erforderlich",
            "failed": "Firmwareupdate wurde mit einem Fehler beendet",
            "reboot-detected": "LTE-Modem wurde während eines laufenden Updates neu gestartet",
            "orphaned-run": "Gespeicherter Update-Vorgang ist nicht mehr aktiv",
            "package-preflight": "Vorprüfung der Update-Datei fehlgeschlagen",
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
            "aborted-before-transfer": "sicher vor Firmwareübertragung abgebrochen",
            "recovery-completed": "Originalzustand wiederhergestellt",
            "failed": "mit Fehler beendet",
            "recovery-required": "manuelle Prüfung erforderlich",
            "reboot-detected": "durch Neustart unterbrochen",
            "orphaned": "gespeicherter Update-Vorgang ist nicht mehr aktiv",
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
            headline = "<b>Bereit:</b> Vorprüfung abgeschlossen; Firmwareupdate wurde noch nicht gestartet."
        elif state == "running":
            headline = "<b>Firmwareupdate läuft auf dem LTE-Modem.</b>"
        else:
            headline = f"<b>Zustand:</b> {escape(state)}"

        abort_text = "möglich" if self._runner_abort_allowed else "nicht möglich"
        transfer_text = "gestartet" if transfer_started else "noch nicht gestartet"
        extra = ""
        if authoritative:
            extra = (
                "<br><b>Hinweis:</b> Das LTE-Modem führt das Update jetzt selbstständig weiter; "
                "ein sicherer Abbruch ist ab dieser Grenze nicht mehr möglich."
            )

        self.runner_status_text.setText(
            headline
            + f"<br><b>Aktueller Schritt:</b> {escape(self._phase_text(phase))}"
            + f"<br><b>Firmwareübertragung:</b> {transfer_text}"
            + f"<br><b>Sicherer Abbruch:</b> {abort_text}"
            + f"<br><b>Wiederherstellung:</b> {escape(self._recovery_text(recovery))}"
            + extra
            + (f"<br><br>{escape(detail)}" if detail else "")
            + (f"<br><small>Lauf-ID: <code>{escape(run_id)}</code></small>" if run_id else "")
        )
        if hasattr(self, "progress_sources"):
            text = self._phase_text(phase)
            if isinstance(board_step, int) and board_step:
                text += " | Mainboard verarbeitet das Update"
            self.progress_sources.setText(text)

    @staticmethod
    def _failed_run_id(output: str) -> str | None:
        match = _FAILED_RUN_RE.search(output)
        return match.group(1) if match else None

    @staticmethod
    def _friendly_failed_preflight(status: dict) -> str:
        reason = str(status.get("reason") or "")
        transfer_started = status.get("transfer_started") is True
        if reason == "package_validation_failed":
            text = (
                "Die Vorprüfung konnte nicht abgeschlossen werden. Möglicherweise ist auf dem "
                "LTE-Modem noch ein unvollständiger vorheriger Updatezustand gespeichert."
            )
        else:
            text = "Die Vorprüfung konnte nicht erfolgreich abgeschlossen werden."
        if not transfer_started:
            text += " Es wurden keine Firmwaredaten an das Mainboard übertragen."
        text += " Technische Details stehen im Protokoll."
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
                    QMessageBox.critical(
                        self,
                        "Vorprüfung fehlgeschlagen",
                        "Die Vorprüfung konnte nicht abgeschlossen werden. Es wurde kein "
                        "Firmwareupdate gestartet. Technische Details stehen im Protokoll.",
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
                    "Die Vorprüfung wurde abgelehnt; der genaue Status konnte nicht automatisch "
                    "gelesen werden. Es wurde kein Firmwareupdate gestartet. Technische Details "
                    "stehen im Protokoll.",
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
