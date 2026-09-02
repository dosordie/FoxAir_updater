from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import foxair_updater_gui as base
import foxair_updater_maintenance as legacy


RUNNER_POLL_MS = 7000


class MainWindow(legacy.MainWindow):
    """Existing FoxAir Windows shell with autonomous DTU OTA orchestration."""

    def __init__(self):
        self._runner_run_id: str | None = None
        self._runner_prepared_manifest: Path | None = None
        self._runner_active = False
        self._runner_abort_allowed = False
        self._runner_terminal = False
        self._runner_acknowledged = False
        self._runner_autostart_after_prepare = False
        self._runner_prepare_mode = "full"
        self._runner_terminal_notified: set[str] = set()
        super().__init__()
        self._runner_timer = QTimer(self)
        self._runner_timer.setInterval(RUNNER_POLL_MS)
        self._runner_timer.timeout.connect(self._poll_runner_status)
        self.setWindowTitle(f"FoxAir Updater {base.APP_VERSION}")

    def _runner_cli(self) -> Path:
        return base.backend_dir() / "tools/dtu_ota_runner/cli.py"

    def _runner_command(self, *args: str) -> list[str] | None:
        adb = self._require_adb()
        if not adb:
            return None
        return [
            str(base.backend_python()),
            str(self._runner_cli()),
            "--adb",
            str(adb),
            *args,
        ]

    def _run_runner(self, op: str, *args: str) -> None:
        command = self._runner_command(*args)
        if command:
            self._run(op, command, str(base.backend_dir()))

    @staticmethod
    def _runner_json(output: str) -> dict | None:
        start = output.find("{")
        if start < 0:
            return None
        try:
            value = json.loads(output[start:])
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def _update(self):
        widget = super()._update()
        layout = widget.layout()
        note = QLabel(
            "<b>Selbstständiges Firmwareupdate:</b> Windows prüft die Update-Datei und startet "
            "den Vorgang. Danach führt das LTE-Modem das Mainboard-Update selbstständig weiter. "
            "Eine unterbrochene Windows- oder ADB-Verbindung beendet das Update nicht."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "QLabel{background:#f7f8fa;border:1px solid #d0d5dd;padding:9px;}"
        )
        layout.insertWidget(0, note)
        self.dry.setText("Vorprüfung")
        self.update_btn.setText("Firmwareupdate starten")
        self.ota_reattach_btn.setText("Update-Status prüfen")
        self.progress.setTextVisible(True)
        return widget

    def _status(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        note = QLabel(
            "<b>Gespeicherter Update-Status:</b> Das LTE-Modem speichert den aktuellen Stand des "
            "Firmwareupdates selbst. Windows liest diesen Zustand nur aus. Ein sicherer Abbruch "
            "ist nur möglich, solange die Firmwareübertragung zum Mainboard noch nicht begonnen hat."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.status_text = QLabel("Noch kein Update-Status gelesen.")
        self.status_text.setWordWrap(True)
        self.status_text.setStyleSheet(
            "QLabel{background:#f7f8fa;border:1px solid #d0d5dd;padding:9px;}"
        )
        layout.addWidget(self.status_text)

        row = QHBoxLayout()
        self.status_btn = QPushButton("Update-Status lesen")
        self.status_btn.clicked.connect(self._status_run)
        row.addWidget(self.status_btn)
        self.runner_log_btn = QPushButton("Technisches Laufprotokoll anzeigen")
        self.runner_log_btn.clicked.connect(self._runner_log)
        row.addWidget(self.runner_log_btn)
        row.addStretch()
        layout.addLayout(row)

        self.restore_btn = QPushButton("Firmwareupdate sicher abbrechen")
        self.restore_btn.clicked.connect(self._restore)
        layout.addWidget(self.restore_btn)

        row = QHBoxLayout()
        self.runner_ack_btn = QPushButton("Abgeschlossenes Ergebnis bestätigen")
        self.runner_ack_btn.clicked.connect(self._runner_ack)
        row.addWidget(self.runner_ack_btn)
        self.runner_cleanup_btn = QPushButton("Gespeicherte Updatedaten löschen")
        self.runner_cleanup_btn.clicked.connect(self._runner_cleanup)
        row.addWidget(self.runner_cleanup_btn)
        row.addStretch()
        layout.addLayout(row)

        lifecycle = QLabel(
            "<b>Normaler Ablauf:</b> Vorprüfung → Firmwareupdate starten → LTE-Modem arbeitet "
            "selbstständig weiter → Ergebnis wird gespeichert → Ergebnis bestätigen → "
            "gespeicherte Updatedaten bei Bedarf löschen."
        )
        lifecycle.setWordWrap(True)
        layout.addWidget(lifecycle)
        layout.addStretch()
        return widget

    def _prepare_runner(self, *, mode: str, autostart: bool) -> None:
        manifest = Path(self.update_manifest.text().strip())
        if mode == "same-version" and hasattr(self, "same_manifest"):
            candidate = Path(self.same_manifest.text().strip())
            if candidate.is_file():
                manifest = candidate
        if not manifest.is_file():
            QMessageBox.warning(self, "Update-Datei fehlt", "Bitte zuerst eine gültige Update-Datei auswählen.")
            return

        self._runner_autostart_after_prepare = autostart
        self._runner_prepare_mode = mode
        self._runner_prepared_manifest = None
        self._runner_acknowledged = False
        args = ["prepare", "--manifest", str(manifest), "--mode", mode]
        if hasattr(self, "restart_before_update") and self.restart_before_update.isChecked():
            args.append("--restart-service-before-update")
        if self.isolate_mqtt.isChecked():
            args.append("--isolate-mqtt")
        self._run_runner("runner-prepare", *args)

    def _dry(self):
        if self._runner_active:
            return
        self._reset_flow("Update-Datei und LTE-Modem werden geprüft", transfer_expected=False)
        self._prepare_runner(mode="full", autostart=False)

    def _update_run(self):
        manifest = Path(self.update_manifest.text().strip())
        if not manifest.is_file() or not self.risk.isChecked() or self._runner_active:
            return
        if (
            QMessageBox.warning(
                self,
                "Firmwareupdate starten",
                "Nach dem Start führt das LTE-Modem das Mainboard-Firmwareupdate selbstständig "
                "weiter. Die Windows- oder ADB-Verbindung darf danach unterbrochen werden, ohne "
                "dass das Update beendet wird.\n\nSobald die Firmwareübertragung zum Mainboard "
                "begonnen hat, ist kein sicherer Abbruch mehr möglich. Wärmepumpe und LTE-Modem "
                "während eines laufenden Updates nicht stromlos machen.\n\n"
                "Firmwareupdate jetzt starten?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return

        self._reset_flow("Firmwareupdate wird vorbereitet", transfer_expected=True)
        prepared = (
            self._runner_run_id
            and self._runner_prepared_manifest is not None
            and self._runner_prepared_manifest.resolve() == manifest.resolve()
            and not self._runner_terminal
            and not self._runner_active
        )
        if prepared:
            self._start_prepared_runner()
        else:
            self._prepare_runner(mode="full", autostart=True)

    def _same(self):
        if self._runner_active:
            return
        self._reset_flow("Prüfung auf gleiche Firmware wird vorbereitet", transfer_expected=False)
        self._prepare_runner(mode="same-version", autostart=True)

    def _start_prepared_runner(self) -> None:
        if not self._runner_run_id:
            QMessageBox.critical(self, "Firmwareupdate", "Kein vorbereitetes Firmwareupdate vorhanden.")
            return
        self._run_runner("runner-start", "start", "--run-id", self._runner_run_id)

    def _status_run(self):
        if self._runner_run_id:
            self._run_runner("runner-status", "status", "--run-id", self._runner_run_id)
        else:
            self._run_runner("runner-current", "current")

    def _runner_log(self):
        if self._runner_run_id:
            self._run_runner("runner-log", "log", "--run-id", self._runner_run_id)
        else:
            self._run_runner("runner-log", "log")

    def _restore(self):
        if not self._runner_run_id:
            QMessageBox.information(
                self, "Abbruch", "Bitte zuerst den aktuellen Update-Status lesen."
            )
            return
        if not self._runner_abort_allowed:
            QMessageBox.warning(
                self,
                "Sicherer Abbruch nicht mehr möglich",
                "Die Firmwareübertragung hat bereits begonnen oder die sichere Abbruchgrenze "
                "wurde überschritten. Das Update wird deshalb nicht erzwungen abgebrochen.",
            )
            return
        if (
            QMessageBox.question(
                self,
                "Firmwareupdate sicher abbrechen",
                "Die Abbruchanforderung wird auf dem LTE-Modem gespeichert. Das LTE-Modem prüft "
                "selbst, ob der Vorgang noch sicher beendet und der Originalzustand "
                "wiederhergestellt werden kann.\n\nAbbruch jetzt anfordern?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        ):
            self._run_runner(
                "runner-abort", "abort-request", "--run-id", self._runner_run_id
            )

    def _runner_ack(self):
        if self._runner_run_id and self._runner_terminal:
            self._run_runner("runner-ack", "ack", "--run-id", self._runner_run_id)

    def _runner_cleanup(self):
        if self._runner_run_id and self._runner_terminal and self._runner_acknowledged:
            if (
                QMessageBox.question(
                    self,
                    "Gespeicherte Updatedaten löschen",
                    "Das bestätigte Endergebnis und die zugehörigen Diagnosedaten werden vom "
                    "LTE-Modem gelöscht. Das hat keinen Einfluss auf die installierte Firmware."
                    "\n\nGespeicherte Updatedaten jetzt löschen?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                == QMessageBox.Yes
            ):
                self._run_runner(
                    "runner-cleanup", "cleanup", "--run-id", self._runner_run_id
                )

    def _reattach_ota(self):
        adb = self._require_adb()
        if not adb:
            return
        runner = [
            str(base.backend_python()),
            str(self._runner_cli()),
            "--adb",
            str(adb),
            "current",
        ]
        self._run_sequence(
            "runner-current",
            [[str(adb), "reconnect"], runner],
            str(base.backend_dir()),
        )

    def _poll_runner_status(self):
        if self.busy or not self._runner_active or not self._runner_run_id:
            return
        self._run_runner("runner-status", "status", "--run-id", self._runner_run_id)

    @staticmethod
    def _phase_text(phase: str) -> str:
        return {
            "dry-run-complete": "Update-Datei und LTE-Modem vollständig geprüft",
            "local-preparation": "Firmwareupdate wird auf dem LTE-Modem vorbereitet",
            "service-restart": "LTE-Kommunikationsdienst wird für das Update neu gestartet",
            "staging": "Firmwaredatei wird für das Update geprüft",
            "hook-started": "Update-Überwachung wurde gestartet",
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
        }.get(phase, phase or "unbekannter Update-Schritt")

    def _render_runner_status(self, status: dict) -> None:
        run_id = str(status.get("run_id") or "")
        if run_id:
            self._runner_run_id = run_id
        state = str(status.get("state") or "?")
        phase = str(status.get("phase") or "?")
        result_type = str(status.get("result_type") or "")
        terminal = status.get("terminal") is True
        abort_allowed = status.get("abort_allowed") is True
        transfer_started = status.get("transfer_started") is True
        authoritative = status.get("original_service_authoritative") is True
        recovery = str(status.get("recovery") or "?")
        detail = str(status.get("detail") or "")
        progress = status.get("progress")
        board_step = status.get("board_ota_step")

        self._runner_terminal = terminal
        self._runner_active = state == "running" and not terminal
        self._runner_abort_allowed = abort_allowed and not terminal
        if terminal:
            self._runner_timer.stop()
        elif self._runner_active and not self._runner_timer.isActive():
            self._runner_timer.start()

        if isinstance(progress, int):
            self.progress.setValue(max(0, min(100, progress)))
            self.progress.setFormat(f"{max(0, min(100, progress))} % – LTE-Modem")
        self.progress_text.setText(self._phase_text(phase))
        if hasattr(self, "progress_sources"):
            extra = self._phase_text(phase)
            if isinstance(board_step, int) and board_step:
                extra += " | Mainboard verarbeitet das Update"
            self.progress_sources.setText(extra)

        if phase == "dry-run-complete":
            self._set_step("runner-preflight", "ok", "Update-Datei, Speicherplatz und LTE-Modem wurden erfolgreich geprüft.")
        if status.get("c350_sent") is True:
            self._set_step("runner-c350", "ok", "Update-Anfrage wurde an das Mainboard gesendet.")
        if status.get("c357_sent") is True:
            self._set_step("runner-c357", "ok", "Firmwareübertragung wurde vorbereitet.")
        if status.get("c5a8_sent") is True or transfer_started:
            self._set_step("runner-c5a8", "warn", "Firmwareübertragung hat begonnen – ein sicherer Abbruch ist jetzt nicht mehr möglich.")
        if authoritative:
            self._set_step("runner-authority", "info", "Der LTE-Dienst führt das Firmwareupdate jetzt selbstständig weiter.")
        if terminal:
            level = "ok" if result_type in {"success", "same-version"} else "warn"
            if result_type in {"failed", "recovery-required", "reboot-detected", "orphaned"}:
                level = "error"
            terminal_text = {
                "success": "Firmwareupdate erfolgreich abgeschlossen.",
                "same-version": "Gleiche Firmware erkannt – kein Update erforderlich.",
                "aborted-before-transfer": "Firmwareupdate wurde sicher vor der Übertragung abgebrochen.",
                "recovery-completed": "Originalzustand wurde erfolgreich wiederhergestellt.",
            }.get(result_type, "Firmwareupdate wurde beendet; bitte Status prüfen.")
            self._set_step("runner-terminal", level, terminal_text)

        abort_text = "möglich" if self._runner_abort_allowed else "nicht möglich"
        transfer_text = "gestartet" if transfer_started else "noch nicht gestartet"
        recovery_text = {
            "not-required": "nicht erforderlich",
            "completed": "abgeschlossen",
            "required": "manuelle Prüfung erforderlich",
            "?": "noch nicht bestimmt",
        }.get(recovery, recovery or "noch nicht bestimmt")
        self.status_text.setText(
            f"<b>Aktueller Schritt:</b> {escape(self._phase_text(phase))}<br>"
            f"<b>Firmwareübertragung:</b> {transfer_text}<br>"
            f"<b>Sicherer Abbruch:</b> {abort_text}<br>"
            f"<b>Wiederherstellung:</b> {escape(recovery_text)}"
            + (f"<br><br>{escape(detail)}" if detail else "")
        )
        self.ota_reattach_btn.setVisible(self._runner_active or bool(self._runner_run_id))
        self._buttons()

        if terminal and run_id and run_id not in self._runner_terminal_notified:
            self._runner_terminal_notified.add(run_id)
            self._show_terminal_result(result_type, phase, detail)

    def _show_terminal_result(self, result_type: str, phase: str, detail: str) -> None:
        result = result_type or phase
        if result == "success":
            self._flow_title = "Firmwareupdate erfolgreich"
            self.progress.setValue(100)
            self.progress.setFormat("100 % – Firmwareupdate abgeschlossen")
            QMessageBox.information(
                self,
                "Firmwareupdate erfolgreich",
                "Das Mainboard-Firmwareupdate wurde erfolgreich abgeschlossen.",
            )
        elif result == "same-version":
            self._flow_title = "Kein Firmwareupdate erforderlich"
            QMessageBox.information(
                self,
                "Gleiche Firmware erkannt",
                "Die gleiche Firmware ist bereits installiert. Es wurden keine Firmwaredaten übertragen.",
            )
        elif result == "aborted-before-transfer":
            self._flow_title = "Firmwareupdate sicher abgebrochen"
            QMessageBox.warning(self, "Update abgebrochen", "Das Firmwareupdate wurde sicher vor Beginn der Übertragung abgebrochen.")
        elif result == "recovery-completed":
            self._flow_title = "Originalzustand wiederhergestellt"
            QMessageBox.warning(self, "Wiederherstellung abgeschlossen", "Der Originalzustand wurde erfolgreich wiederhergestellt.")
        else:
            self._flow_title = "Manuelle Prüfung erforderlich"
            QMessageBox.critical(
                self,
                "Firmwareupdate nicht erfolgreich abgeschlossen",
                "Das Firmwareupdate konnte nicht sicher als erfolgreich abgeschlossen bestätigt werden. "
                "Bitte das technische Protokoll sichern und den Status prüfen.",
            )
        self._render_flow()

    def _done(self, op, code, output):
        if not op.startswith("runner-"):
            super()._done(op, code, output)
            return

        super()._done("handled-result", code, output)

        if op == "runner-log":
            if code != 0:
                QMessageBox.warning(self, "Technisches Laufprotokoll", "Das technische Laufprotokoll konnte nicht gelesen werden.")
            return

        if op == "runner-cleanup":
            if code == 0:
                self._log("[DTU Runner] bestätigter Run wurde aufgeräumt.")
                self._runner_run_id = None
                self._runner_prepared_manifest = None
                self._runner_active = False
                self._runner_terminal = False
                self._runner_abort_allowed = False
                self._runner_acknowledged = False
                self.ota_reattach_btn.setVisible(False)
                self.status_text.setText("Gespeicherte Updatedaten wurden gelöscht.")
                self._buttons()
            else:
                QMessageBox.critical(self, "Löschen fehlgeschlagen", "Die gespeicherten Updatedaten konnten nicht gelöscht werden. Diagnosedaten bleiben erhalten.")
            return

        status = self._runner_json(output)
        if code != 0 or status is None or status.get("ok") is False:
            if op in {"runner-status", "runner-current"} and self._runner_active:
                self.progress_text.setText(
                    "ADB-Verbindung nicht verfügbar – das LTE-Modem arbeitet selbstständig weiter."
                )
                self._set_step(
                    "runner-adb-lost",
                    "warn",
                    "Windows kann den aktuellen Status momentan nicht lesen. Das Firmwareupdate auf dem LTE-Modem wird dadurch nicht gestoppt.",
                )
                self.ota_reattach_btn.setVisible(True)
                self._render_flow()
                return
            QMessageBox.critical(
                self,
                "Firmwareupdate",
                "Der angeforderte Update-Vorgang konnte nicht ausgeführt werden. Details stehen im technischen Protokoll."
                + (f"\n\n{status.get('error')}" if isinstance(status, dict) and status.get("error") else ""),
            )
            return

        if op == "runner-prepare":
            self._runner_run_id = str(status.get("run_id") or "") or None
            manifest = Path(self.update_manifest.text().strip())
            if self._runner_prepare_mode == "same-version" and hasattr(self, "same_manifest"):
                candidate = Path(self.same_manifest.text().strip())
                if candidate.is_file():
                    manifest = candidate
            self._runner_prepared_manifest = manifest if manifest.is_file() else None
            self._render_runner_status(status)
            if status.get("phase") != "dry-run-complete":
                QMessageBox.critical(self, "Vorprüfung", "Die Vorprüfung konnte nicht vollständig bestätigt werden. Details stehen im technischen Protokoll.")
                self._runner_autostart_after_prepare = False
                return
            self._set_step("runner-prepared", "ok", "Firmwareupdate ist vollständig vorbereitet. Es wurde noch nichts an das Mainboard übertragen.")
            if self._runner_autostart_after_prepare:
                self._runner_autostart_after_prepare = False
                QTimer.singleShot(150, self._start_prepared_runner)
            else:
                QMessageBox.information(
                    self,
                    "Vorprüfung erfolgreich",
                    "Update-Datei und LTE-Modem wurden vollständig geprüft. Das Firmwareupdate "
                    "wurde noch nicht gestartet und es wurden keine Firmwaredaten an das Mainboard übertragen.",
                )
            return

        if op in {"runner-start", "runner-status", "runner-current", "runner-abort", "runner-ack"}:
            self._render_runner_status(status)
            if op == "runner-start":
                self._runner_active = status.get("terminal") is not True
                if self._runner_active and not self._runner_timer.isActive():
                    self._runner_timer.start()
                self._set_step("runner-detached", "ok", "Firmwareupdate wurde auf dem LTE-Modem gestartet und läuft dort selbstständig weiter.")
            elif op == "runner-abort":
                self._set_step("runner-abort-request", "warn", "Sicherer Abbruch wurde angefordert. Das LTE-Modem prüft, ob der Vorgang noch sicher beendet werden kann.")
            elif op == "runner-ack":
                self._runner_acknowledged = True
                self._log("[DTU Runner] terminales Ergebnis wurde bestätigt (ACK).")
                self._buttons()
            return

    def _buttons(self):
        super()._buttons()
        if not hasattr(self, "status_btn"):
            return
        enabled = not self.busy
        adb_ready = self._adb_ready()
        manifest_ready = Path(self.update_manifest.text().strip()).is_file()
        if self._runner_active:
            self.dry.setEnabled(False)
            self.update_btn.setEnabled(False)
        else:
            self.dry.setEnabled(enabled and adb_ready and manifest_ready)
            self.update_btn.setEnabled(enabled and adb_ready and manifest_ready and self.risk.isChecked())
        self.status_btn.setEnabled(enabled and adb_ready)
        self.runner_log_btn.setEnabled(enabled and adb_ready)
        self.restore_btn.setEnabled(enabled and adb_ready and self._runner_abort_allowed)
        self.runner_ack_btn.setEnabled(enabled and adb_ready and self._runner_terminal)
        self.runner_cleanup_btn.setEnabled(
            enabled and adb_ready and self._runner_terminal and self._runner_acknowledged
        )
        self.ota_reattach_btn.setEnabled(enabled and adb_ready)


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
