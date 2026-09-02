from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

import foxair_updater_gui as base
import foxair_updater_runner_product as product


CLEAN_DTU_CONFIRM_TOKEN = "FOXAIR-DTU-CLEAN"
AUTO_FINALIZE_RESULTS = {"success", "same-version"}


class MainWindow(product.MainWindow):
    """Release entrypoint with one-click support diagnostics and safe DTU cleanup."""

    def __init__(self):
        self._auto_finalize_started: set[str] = set()
        self._auto_finalize_run_id: str | None = None
        self._auto_finalize_archive: Path | None = None
        self._auto_cleanup_retry_visible = False
        super().__init__()

    def _status(self):
        widget = super()._status()
        layout = widget.layout()

        # The clean-DTU option belongs directly next to the real
        # "Originalzustand wiederherstellen" button.  The button lives inside a
        # QGroupBox, therefore start the recursive layout lookup at its parent
        # widget instead of at the status page's outer layout.
        restore_parent = self.original_restore_btn.parentWidget()
        restore_parent_layout = restore_parent.layout() if restore_parent is not None else None
        restore_row = self._layout_containing(
            restore_parent_layout, self.original_restore_btn
        )
        self.clean_dtu_after_restore = QCheckBox(
            "Danach alle FoxAir-Updater-Dateien vom LTE-Modem entfernen"
        )
        self.clean_dtu_after_restore.setToolTip(
            "Nur verwenden, wenn kein Update läuft. Entfernt ausschließlich Arbeitsdateien, "
            "Hooks, temporäre Statusdateien und Runner-Verzeichnisse des FoxAir Updaters. "
            "Originale PHNIX-Dateien, Firmware, OTA_INFO und Statistik werden nicht gelöscht."
        )
        if restore_row is not None:
            insert_at = restore_row.indexOf(self.original_restore_btn)
            restore_row.insertWidget(insert_at + 1, self.clean_dtu_after_restore)
        else:
            # Defensive fallback if the inherited status layout changes later.
            fallback_row = QHBoxLayout()
            fallback_row.addWidget(self.clean_dtu_after_restore)
            fallback_row.addStretch()
            layout.insertLayout(1, fallback_row)

        # Successful/same-version terminal runs are now archived and cleaned up
        # automatically.  Keep the old lifecycle controls instantiated for
        # compatibility, but hide the manual two-step flow from the normal UI.
        self.runner_ack_btn.setVisible(False)
        self.runner_cleanup_btn.setVisible(False)
        for label in widget.findChildren(QLabel):
            text = label.text()
            if "<b>Normaler Ablauf:</b>" in text and "Ergebnis bestätigen" in text:
                label.setText(
                    "<b>Normaler Ablauf:</b> Vorprüfung → Firmwareupdate starten → LTE-Modem "
                    "arbeitet selbstständig weiter → Endergebnis wird gespeichert → bei Erfolg "
                    "oder gleicher Firmware werden die DTU-Protokolle automatisch lokal gesichert "
                    "und die gespeicherten Updatedaten anschließend vom LTE-Modem entfernt."
                )
                break
        return widget

    def _ui(self):
        super()._ui()
        clear_button = next(
            (
                button
                for button in self.findChildren(QPushButton)
                if button.text() == "Protokoll leeren"
            ),
            None,
        )
        root_layout = self.centralWidget().layout() if self.centralWidget() else None
        toolbar = self._layout_containing(root_layout, clear_button)
        if toolbar is None or clear_button is None:
            return
        self.diagnostics_button = QPushButton("Diagnosepaket speichern…")
        self.diagnostics_button.setToolTip(
            "Speichert den sichtbaren GUI-Log sowie die Textdiagnose aller DTU-OTA-Versuche "
            "des betreffenden Tages als ZIP. Firmware, OTA_INFO und Statistik-Binärdaten "
            "werden nicht eingebunden."
        )
        self.diagnostics_button.clicked.connect(self._save_diagnostic_bundle)
        toolbar.insertWidget(max(0, toolbar.indexOf(clear_button)), self.diagnostics_button)

    @staticmethod
    def _diagnostics_core_path() -> Path:
        return base.backend_dir() / "updater/dtu_ota/diagnostics.py"

    @staticmethod
    def _cleanup_core_path() -> Path:
        return base.backend_dir() / "updater/dtu_ota/cleanup.py"

    def _original_restore(self):
        """Restore original operation, optionally followed by fail-closed cleanup."""
        if not getattr(self, "clean_dtu_after_restore", None) or not self.clean_dtu_after_restore.isChecked():
            super()._original_restore()
            return
        if self.busy:
            return
        if self._runner_active:
            QMessageBox.warning(
                self,
                "Firmwareupdate läuft",
                "Während eines laufenden Firmwareupdates wird weder der Originalzustand erzwungen "
                "noch die DTU bereinigt.",
            )
            return
        adb = self._require_adb()
        if not adb:
            return
        core = self._cleanup_core_path()
        if not core.is_file():
            QMessageBox.critical(
                self,
                "DTU-Bereinigung fehlt",
                f"Der Cleanup-Core wurde nicht gefunden:\n{core}",
            )
            return

        if (
            QMessageBox.warning(
                self,
                "Originalzustand wiederherstellen und DTU bereinigen?",
                "Der Updater prüft zuerst fail-closed, dass kein FoxAir-Mainboard-Update mehr "
                "läuft. Anschließend wird der normale Originalbetrieb wiederhergestellt und "
                "danach werden ausschließlich die vom FoxAir Updater angelegten Arbeitsdateien "
                "vom LTE-Modem entfernt.\n\n"
                "Nicht gelöscht werden originale PHNIX-Dateien, Firmware, OTA_INFO oder die "
                "Statistikdatei. Bereits entstandene Statistikzähler oder Cloud-/Serverhistorie "
                "können dadurch ebenfalls nicht rückwirkend entfernt werden.\n\n"
                "DTU jetzt wiederherstellen und bereinigen?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return

        python = str(base.backend_python())
        adb_path = str(adb)
        cleanup_check = [python, str(core), "--adb", adb_path, "check"]
        restore = [
            python,
            str(self.controller),
            "--adb",
            adb_path,
            "--output",
            "json",
            "--no-color",
            "run",
            "--restore",
            "original",
        ]
        cleanup = [
            python,
            str(core),
            "--adb",
            adb_path,
            "--execute",
            "--confirm",
            CLEAN_DTU_CONFIRM_TOKEN,
            "clean",
        ]
        self._run_sequence(
            "restore-clean",
            [cleanup_check, restore, cleanup],
            str(base.backend_dir()),
        )

    def _buttons(self):
        super()._buttons()
        checkbox = getattr(self, "clean_dtu_after_restore", None)
        if checkbox is not None:
            checkbox.setEnabled(
                not self.busy and self._adb_ready() and not self._runner_active
            )
        if hasattr(self, "runner_ack_btn"):
            self.runner_ack_btn.setVisible(False)
        if hasattr(self, "runner_cleanup_btn"):
            self.runner_cleanup_btn.setVisible(self._auto_cleanup_retry_visible)
            if self._auto_cleanup_retry_visible:
                self.runner_cleanup_btn.setText("Gespeicherte Updatedaten erneut löschen")

    def _diagnostic_log_directory(self) -> Path:
        """Use the same directory in which automatic update logs are stored."""
        manifest_text = self.update_manifest.text().strip() if hasattr(self, "update_manifest") else ""
        manifest = Path(manifest_text) if manifest_text else None
        if manifest is not None and manifest.is_file():
            firmware_directory = manifest.parent
            logs = firmware_directory / "Logs"
            try:
                logs.mkdir(exist_ok=True)
                return logs
            except OSError:
                return firmware_directory
        return base.data_dir()

    def _save_diagnostic_bundle(self) -> None:
        if self.busy:
            return
        adb = self._require_adb()
        if not adb:
            return
        core = self._diagnostics_core_path()
        if not core.is_file():
            QMessageBox.critical(
                self,
                "Diagnosefunktion fehlt",
                f"Der Diagnose-Core wurde nicht gefunden:\n{core}",
            )
            return

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_directory = self._diagnostic_log_directory()
        default = log_directory / f"FoxAir_Diagnose_{stamp}.zip"
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Diagnosepaket speichern",
            str(default),
            "ZIP (*.zip)",
        )
        if not file_name:
            return
        output = Path(file_name)
        if output.suffix.lower() != ".zip":
            output = output.with_suffix(".zip")

        host_log = base.data_dir() / "diagnostics-current-gui.log"
        try:
            host_log.write_text(self.log.toPlainText(), encoding="utf-8")
        except OSError as error:
            QMessageBox.critical(self, "Diagnosepaket", f"GUI-Protokoll konnte nicht vorbereitet werden:\n{error}")
            return

        self._diagnostic_output = output
        self._diagnostic_host_log = host_log
        command = [
            str(base.backend_python()),
            str(core),
            "--adb",
            str(adb),
            "--output",
            str(output),
            "--host-log",
            str(host_log),
            "--host-log-dir",
            str(log_directory),
            "--app-version",
            base.APP_VERSION,
        ]
        run_id = getattr(self, "_runner_run_id", None)
        if isinstance(run_id, str) and run_id.strip():
            command += ["--run-id", run_id.strip()]
        self._run("runner-diagnostics", command, str(base.backend_dir()))

    def _schedule_terminal_auto_finalize(self, status: dict) -> None:
        run_id = str(status.get("run_id") or "").strip()
        result_type = str(status.get("result_type") or "").strip()
        if (
            status.get("terminal") is not True
            or result_type not in AUTO_FINALIZE_RESULTS
            or not run_id
            or run_id in self._auto_finalize_started
        ):
            return
        self._auto_finalize_started.add(run_id)
        QTimer.singleShot(300, lambda rid=run_id: self._start_terminal_auto_archive(rid))

    def _start_terminal_auto_archive(self, run_id: str) -> None:
        if self.busy:
            QTimer.singleShot(300, lambda rid=run_id: self._start_terminal_auto_archive(rid))
            return
        adb = self._require_adb()
        core = self._diagnostics_core_path()
        if not adb or not core.is_file():
            self._auto_finalize_started.discard(run_id)
            QMessageBox.warning(
                self,
                "DTU-Protokolle bleiben erhalten",
                "Das sichere lokale Archiv konnte nicht gestartet werden. Die gespeicherten "
                "Updatedaten werden deshalb nicht vom LTE-Modem gelöscht.",
            )
            return

        log_directory = self._diagnostic_log_directory()
        archive = log_directory / f"FoxAir_DTU_Logs_{run_id}.zip"
        self._auto_finalize_run_id = run_id
        self._auto_finalize_archive = archive
        self._auto_cleanup_retry_visible = False
        self._log(f"[DTU Runner] sichere lokale Archivierung für {run_id} wird gestartet.")
        command = [
            str(base.backend_python()),
            str(core),
            "--adb",
            str(adb),
            "--output",
            str(archive),
            "--host-log-dir",
            str(log_directory),
            "--app-version",
            base.APP_VERSION,
            "--run-id",
            run_id,
        ]
        self._run("runner-auto-diagnostics", command, str(base.backend_dir()))

    def _render_runner_status(self, status: dict) -> None:
        super()._render_runner_status(status)
        self._schedule_terminal_auto_finalize(status)

    def _show_runner_log_dialog(self, output: str) -> None:
        """Show the fetched DTU runner.log instead of silently writing it to the GUI log."""
        dialog = QDialog(self)
        run_id = str(getattr(self, "_runner_run_id", "") or "").strip()
        title = "Technisches Laufprotokoll"
        if run_id:
            title += f" – {run_id}"
        dialog.setWindowTitle(title)
        dialog.resize(920, 620)

        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(dialog)
        text.setReadOnly(True)
        text.setLineWrapMode(QPlainTextEdit.NoWrap)
        text.setPlainText(output.rstrip() or "(Für diesen Lauf ist kein runner.log-Inhalt vorhanden.)")
        layout.addWidget(text, 1)

        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton("Schließen", dialog)
        close.clicked.connect(dialog.accept)
        row.addWidget(close)
        layout.addLayout(row)
        dialog.exec()

    @staticmethod
    def _last_json_record(output: str) -> dict | None:
        for line in reversed(output.splitlines()):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        return None

    def _auto_finalize_failed(self, title: str, message: str) -> None:
        run_id = self._auto_finalize_run_id
        if run_id:
            self._auto_finalize_started.discard(run_id)
        self._auto_finalize_run_id = None
        self._auto_finalize_archive = None
        QMessageBox.warning(self, title, message)

    def _done(self, op, code, output):
        if op == "restore-clean":
            super()._done("handled-result", code, output)
            parsed = self._last_json_record(output)
            if code == 0 and parsed and parsed.get("ok") is True:
                QMessageBox.information(
                    self,
                    "DTU bereinigt",
                    "Der normale Originalbetrieb wurde wiederhergestellt und alle bekannten "
                    "FoxAir-Updater-Arbeitsdateien wurden vom LTE-Modem entfernt.\n\n"
                    "Originale PHNIX-Dateien, Firmware, OTA_INFO und Statistik wurden nicht verändert.",
                )
                self.clean_dtu_after_restore.setChecked(False)
                return
            detail = parsed.get("error") if isinstance(parsed, dict) else None
            QMessageBox.critical(
                self,
                "DTU-Bereinigung nicht durchgeführt",
                "Die Wiederherstellung/Bereinigung wurde abgebrochen. "
                "Wenn ein Update oder ein nicht eindeutig sicherer OTA-Zustand erkannt wird, "
                "löscht der Cleanup-Core absichtlich nichts."
                + (f"\n\n{detail}" if detail else "")
                + "\n\nDetails stehen im Protokoll.",
            )
            return

        if op == "runner-log":
            # The inherited implementation fetches runner.log correctly but only
            # writes the subprocess output to the general application protocol.
            # The button explicitly says "anzeigen", so present the content.
            super()._done(op, code, output)
            if code == 0:
                self._show_runner_log_dialog(output)
            return

        if op == "runner-auto-diagnostics":
            super()._done("handled-result", code, output)
            parsed = self._last_json_record(output)
            run_id = self._auto_finalize_run_id
            archive = self._auto_finalize_archive
            archive_ok = isinstance(archive, Path) and archive.is_file()
            if code == 0 and parsed and parsed.get("ok") is True and run_id and archive_ok:
                self._log(f"[DTU Runner] DTU-Protokolle lokal gesichert: {archive}")
                self._run_runner("runner-auto-ack", "ack", "--run-id", run_id)
                return
            self._auto_finalize_failed(
                "DTU-Protokolle bleiben erhalten",
                "Die DTU-Protokolle konnten nicht eindeutig lokal gesichert und verifiziert "
                "werden. Deshalb werden die gespeicherten Updatedaten nicht vom LTE-Modem "
                "gelöscht. Der manuelle Diagnose-Export bleibt verfügbar.",
            )
            return

        if op == "runner-auto-ack":
            super()._done("handled-result", code, output)
            run_id = self._auto_finalize_run_id
            status = self._runner_json(output)
            if code == 0 and isinstance(status, dict) and run_id:
                self._runner_acknowledged = True
                self._run_runner("runner-auto-cleanup", "cleanup", "--run-id", run_id)
                return
            self._auto_finalize_failed(
                "Gespeicherte Updatedaten bleiben erhalten",
                "Das lokal gesicherte Endergebnis konnte auf dem LTE-Modem nicht automatisch "
                "bestätigt werden. Deshalb wird kein Cleanup ausgeführt.",
            )
            return

        if op == "runner-auto-cleanup":
            super()._done("handled-result", code, output)
            parsed = self._last_json_record(output)
            run_id = self._auto_finalize_run_id
            archive = self._auto_finalize_archive
            if code == 0 and parsed and parsed.get("ok") is True and parsed.get("cleaned") is True:
                self._log(
                    f"[DTU Runner] {run_id}: DTU-Protokolle lokal gesichert und gespeicherte "
                    "Updatedaten automatisch entfernt."
                )
                current = self.runner_status_text.text()
                self.runner_status_text.setText(
                    current
                    + "<br><br><b>✓ DTU-Protokolle lokal gesichert.</b>"
                    + "<br><b>✓ Gespeicherte Updatedaten vom LTE-Modem entfernt.</b>"
                    + (f"<br><small>{archive}</small>" if archive else "")
                )
                self._runner_run_id = None
                self._runner_prepared_manifest = None
                self._runner_active = False
                self._runner_terminal = False
                self._runner_abort_allowed = False
                self._runner_acknowledged = False
                self._auto_finalize_run_id = None
                self._auto_finalize_archive = None
                self._auto_cleanup_retry_visible = False
                self.ota_reattach_btn.setVisible(False)
                self._buttons()
                return

            # ACK succeeded, so a failed cleanup can safely be retried manually.
            self._auto_cleanup_retry_visible = True
            self._runner_acknowledged = True
            self._buttons()
            QMessageBox.warning(
                self,
                "Automatisches Aufräumen fehlgeschlagen",
                "Die DTU-Protokolle wurden bereits lokal gesichert und das Endergebnis wurde "
                "bestätigt, aber die gespeicherten Updatedaten konnten nicht automatisch "
                "entfernt werden. Die Daten bleiben auf dem LTE-Modem erhalten; der eingeblendete "
                "Cleanup-Button kann für einen erneuten Versuch verwendet werden.",
            )
            return

        if op == "runner-cleanup":
            super()._done(op, code, output)
            if code == 0:
                self._auto_cleanup_retry_visible = False
                self._buttons()
            return

        if op != "runner-diagnostics":
            super()._done(op, code, output)
            return

        super()._done("handled-result", code, output)
        host_log = getattr(self, "_diagnostic_host_log", None)
        if isinstance(host_log, Path):
            try:
                host_log.unlink(missing_ok=True)
            except OSError:
                pass

        parsed = None
        for line in reversed(output.splitlines()):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "ok" in value:
                parsed = value
                break

        if code == 0 and parsed and parsed.get("ok") is True:
            missing = parsed.get("missing") or {}
            suffix = ""
            if isinstance(missing, dict) and missing:
                suffix = "\n\nEinige optionale Dateien waren nicht vorhanden; dies ist bei manchen Laufphasen normal."
            run_ids = parsed.get("run_ids") or []
            attempts = len(run_ids) if isinstance(run_ids, list) else 1
            host_logs = parsed.get("host_logs") or []
            host_count = len(host_logs) if isinstance(host_logs, list) else 0
            QMessageBox.information(
                self,
                "Diagnosepaket gespeichert",
                f"Das Diagnosepaket wurde gespeichert:\n{parsed.get('output', self._diagnostic_output)}"
                f"\n\nEnthaltene DTU-OTA-Versuche dieses Tages: {attempts}"
                f"\nZusätzliche Windows-Update-Logs dieses Tages: {host_count}"
                "\n\nFirmware, OTA_INFO und Statistik-Binärdaten wurden nicht eingebunden. "
                "Bekannte Geräte-/Cloudkennungen werden in Textdateien maskiert."
                + suffix,
            )
            return

        detail = parsed.get("error") if isinstance(parsed, dict) else "Unbekannter Fehler"
        QMessageBox.critical(
            self,
            "Diagnosepaket fehlgeschlagen",
            f"Das Diagnosepaket konnte nicht erstellt werden.\n\n{detail}\n\nDetails stehen im Protokoll.",
        )


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
