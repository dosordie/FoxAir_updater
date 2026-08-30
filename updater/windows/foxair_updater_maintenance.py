from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
)

import foxair_updater_operator_display as operator
import foxair_updater_traffic as traffic
from updater.common.adb_transport import AdbClient
from updater.common.phnix_modem_info import PhnixModemInfo
from updater.common.phnix_service_restart import restart_phnix_iot_service


CONFIRM_TOKEN = "PHNIX-STATISTICS-WRITE"


class RestartSignals(QObject):
    done = Signal(bool, str)


class MainWindow(traffic.MainWindow):
    """Thin frontend for the shared statistics maintenance core."""

    def __init__(self):
        self._restart_signals = RestartSignals()
        self._restart_signals.done.connect(self._restart_finished)
        super().__init__()
        self._update_window_title()

    def _update_window_title(self) -> None:
        if self.adb_remote.isChecked():
            host = self.remote_host.text().strip()
            connection = f"Remote ADB {host}" if host else "Remote ADB"
        else:
            connection = "USB"
        version = operator.lte.desktop.app.APP_VERSION
        self.setWindowTitle(f"FoxAir Updater {version} – {connection}")

    def _remote_changed(self, *args):
        super()._remote_changed(*args)
        if hasattr(self, "adb_remote") and hasattr(self, "remote_host"):
            self._update_window_title()

    def _update(self):
        widget = super()._update()
        phase_font = self.progress_text.font()
        phase_font.setPointSize(max(13, phase_font.pointSize() + 1))
        phase_font.setBold(True)
        self.progress_text.setFont(phase_font)
        return widget

    @staticmethod
    def _byte_progress_text(offset: int | None, length: int | None) -> str:
        if isinstance(offset, int) and isinstance(length, int) and length > 0:
            return (
                f"100 % – {offset:,} / {length:,} Byte – Übertragung abgeschlossen"
            ).replace(",", ".")
        return "100 % – Übertragung abgeschlossen"

    def _render_post_transfer_phase(self, phase: str) -> None:
        phases = {
            "transfer-complete": (
                "transfer-complete",
                "ok",
                "Firmwareübertragung vollständig abgeschlossen.",
                "Übertragung abgeschlossen – Firmware wird im Staging-Bereich geprüft.",
                "100 % – Übertragung abgeschlossen",
            ),
            "staging-verified": (
                "staging-verified",
                "ok",
                "Staging-Firmware wurde vollständig geprüft.",
                "Staging-Prüfung erfolgreich – Mainboard bereitet die Übernahme vor.",
                "100 % – Staging geprüft",
            ),
            "promotion": (
                "promotion",
                "warn",
                "Mainboard übernimmt die geprüfte Firmware in den Zielbereich.",
                "Firmware wird auf dem Mainboard übernommen.",
                "100 % – Firmware wird übernommen",
            ),
            "promotion-committed": (
                "promotion-committed",
                "ok",
                "Firmware wurde geprüft, übernommen und als Zielversion bestätigt.",
                "Firmware übernommen – Mainboard-Abschluss läuft.",
                "100 % – Firmware übernommen",
            ),
            "restoring-original": (
                "restoring-original",
                "warn",
                "LTE-Originalbetrieb wird nach dem Mainboard-Update wiederhergestellt.",
                "Mainboard-Update abgeschlossen – LTE-Originalbetrieb wird wiederhergestellt.",
                "100 % – Originalbetrieb wird wiederhergestellt",
            ),
            "success": (
                "phase-success",
                "ok",
                "Mainboard-Firmwareupdate wurde erfolgreich abgeschlossen.",
                "Mainboard-Update erfolgreich – Originalbetrieb wird abschließend geprüft.",
                "100 % – Mainboard-Update erfolgreich",
            ),
        }
        item = phases.get(phase)
        if not item:
            return
        key, level, step_text, large_text, progress_text = item
        self._set_step(key, level, step_text)
        self.progress_text.setText(large_text)
        self.progress.setValue(100)
        self.progress.setFormat(progress_text)

    def _handle_record(self, record: dict):
        super()._handle_record(record)

        event = record.get("event")
        if event == "transfer-complete":
            offset = record.get("offset")
            length = record.get("length")
            self._set_step(
                "transfer-complete",
                "ok",
                (
                    f"Firmwareübertragung vollständig: {offset:,} / {length:,} Byte."
                ).replace(",", ".")
                if isinstance(offset, int) and isinstance(length, int) and length > 0
                else "Firmwareübertragung vollständig abgeschlossen.",
            )
            self.progress_text.setText(
                "Übertragung abgeschlossen – Firmware wird im Staging-Bereich geprüft."
            )
            self.progress.setValue(100)
            self.progress.setFormat(self._byte_progress_text(offset, length))
        elif event == "services-restored" and record.get("ok") is True:
            self.progress_text.setText(
                "Firmwareupdate erfolgreich – LTE-/Cloudzustand ist vollständig geprüft."
            )
            self.progress.setValue(100)
            self.progress.setFormat("100 % – Firmwareupdate erfolgreich abgeschlossen")

        phase = self._record_phase(record)
        if phase:
            self._render_post_transfer_phase(phase)

    def _advanced(self):
        widget = super()._advanced()
        layout = widget.layout()
        insert_at = max(0, layout.count() - 1)

        heading = QLabel(
            "<hr><b>Wartung – Mainboard OTA-Vorgänge</b>"
        )
        layout.insertWidget(insert_at, heading)
        insert_at += 1

        note = QLabel(
            "Diese Funktion verwendet einen <b>eigenständigen gemeinsamen "
            "Windows/Linux-Core</b>. Der bestehende OTA-Controller wird nicht "
            "verändert oder aufgerufen. Der Core prüft den Originalzustand, "
            "hält die Watchdogs kurz an, beendet <code>phnixIot4G</code> sauber, "
            "sichert die vollständige 128-Byte-Statistikdatei, ändert ausschließlich "
            "den uint32-Wert bei Offset <code>0x24</code>, startet den Originaldienst "
            "wieder und verifiziert Datei und RAM. Es werden keine RS485-/Modbus-"
            "Telegramme gesendet."
        )
        note.setWordWrap(True)
        layout.insertWidget(insert_at, note)
        insert_at += 1

        self.statistics_current = QLabel(
            "Aktueller Wert: noch nicht mit dem Maintenance-Core geprüft."
        )
        self.statistics_current.setWordWrap(True)
        layout.insertWidget(insert_at, self.statistics_current)
        insert_at += 1

        row = QHBoxLayout()
        self.statistics_target = QLineEdit("0")
        self.statistics_target.setPlaceholderText("0 … 4294967295")
        self.statistics_target.textChanged.connect(self._buttons)
        row.addWidget(QLabel("Neuer Wert:"))
        row.addWidget(self.statistics_target, 1)
        self.statistics_show_btn = QPushButton("Aktuellen Wert prüfen")
        self.statistics_show_btn.clicked.connect(self._statistics_show)
        row.addWidget(self.statistics_show_btn)
        layout.insertLayout(insert_at, row)
        insert_at += 1

        self.allow_statistics_write = QCheckBox(
            "Ändern des persistenten Statistikzustands erlauben"
        )
        self.allow_statistics_write.toggled.connect(self._buttons)
        layout.insertWidget(insert_at, self.allow_statistics_write)
        insert_at += 1

        self.statistics_set_btn = QPushButton("Mainboard OTA-Vorgänge setzen")
        self.statistics_set_btn.clicked.connect(self._statistics_set)
        layout.insertWidget(insert_at, self.statistics_set_btn)
        insert_at += 1

        layout.insertWidget(insert_at, QLabel("<hr><b>PHNIX-LTE-Kommunikationsdienst</b>"))
        insert_at += 1
        restart_note = QLabel(
            "Startet ausschließlich den PHNIX-LTE-Kommunikationsdienst neu. "
            "Das LTE-Modem/Linux-System wird nicht neu gestartet."
        )
        restart_note.setWordWrap(True)
        layout.insertWidget(insert_at, restart_note)
        insert_at += 1
        self.phnix_restart_btn = QPushButton("phnixIot4G neu starten")
        self.phnix_restart_btn.clicked.connect(self._restart_phnix_iot)
        layout.insertWidget(insert_at, self.phnix_restart_btn)
        return widget

    def _restart_phnix_iot(self):
        if self.busy:
            return
        if (
            QMessageBox.question(
                self,
                "phnixIot4G neu starten",
                "Der PHNIX-LTE-Kommunikationsdienst wird kurz beendet und vom "
                "Geräte-Watchdog neu gestartet.\nCloud-/LTE-Kommunikation ist "
                "währenddessen kurz unterbrochen.\n\nJetzt neu starten?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        adb_path = self._require_adb()
        if not adb_path:
            return
        self.busy = True
        self._buttons()
        client = AdbClient(adb_path, env=self._process_env())

        def work():
            try:
                message = restart_phnix_iot_service(client)
            except Exception as error:
                self._restart_signals.done.emit(False, str(error))
            else:
                self._restart_signals.done.emit(True, message)

        threading.Thread(target=work, daemon=True, name="phnix-service-restart").start()

    def _restart_finished(self, success: bool, message: str):
        self.busy = False
        self._buttons()
        if success:
            QMessageBox.information(self, "phnixIot4G neu starten", message)
        else:
            QMessageBox.warning(self, "phnixIot4G neu starten", message)

    @staticmethod
    def _statistics_core_path() -> Path:
        return (
            operator.lte.desktop.app.base.backend_dir()
            / "updater"
            / "common"
            / "phnix_statistics_maintenance.py"
        )

    def _statistics_backup_dir(self) -> Path:
        text = self.backup_path.text().strip()
        base = Path(text) if text else Path.home() / "FoxAir_LTE_Backup"
        return base / "statistics-maintenance"

    def _statistics_value(self) -> int | None:
        text = self.statistics_target.text().strip()
        try:
            value = int(text, 10)
        except ValueError:
            return None
        return value if 0 <= value <= 0xFFFFFFFF else None

    def _statistics_command(self, adb: Path, *args: str) -> list[str]:
        return [
            str(operator.lte.desktop.app.base.backend_python()),
            str(self._statistics_core_path()),
            "--adb",
            str(adb),
            "--output",
            "json",
            *args,
        ]

    def _statistics_show(self):
        adb = self._require_adb()
        if not adb:
            return
        core = self._statistics_core_path()
        if not core.is_file():
            QMessageBox.critical(
                self,
                "Maintenance-Core fehlt",
                f"Der gemeinsame Maintenance-Core wurde nicht gefunden:\n{core}",
            )
            return
        self._run(
            "statistics-show",
            self._statistics_command(adb, "show"),
            str(operator.lte.desktop.app.base.backend_dir()),
        )

    def _statistics_set(self):
        if self.busy or not self.allow_statistics_write.isChecked():
            return
        value = self._statistics_value()
        if value is None:
            QMessageBox.warning(
                self,
                "Ungültiger Wert",
                "Bitte einen ganzzahligen uint32-Wert zwischen 0 und 4294967295 eingeben.",
            )
            return
        adb = self._require_adb()
        if not adb:
            return
        core = self._statistics_core_path()
        if not core.is_file():
            QMessageBox.critical(
                self,
                "Maintenance-Core fehlt",
                f"Der gemeinsame Maintenance-Core wurde nicht gefunden:\n{core}",
            )
            return

        current = self.statistics_current.text().replace("Aktueller Wert:", "").strip()
        if (
            QMessageBox.warning(
                self,
                "Mainboard OTA-Vorgänge ändern?",
                "Der bestehende OTA-Controller bleibt unberührt. Der separate "
                "Maintenance-Core wird den Originaldienst für wenige Sekunden "
                "kontrolliert stoppen und anschließend wieder starten.\n\n"
                f"Aktuell angezeigt: {current}\n"
                f"Neuer Wert: {value}\n\n"
                "Vor dem Schreiben wird die komplette 128-Byte-Statistikdatei "
                "lokal gesichert. Nur Offset 0x24..0x27 darf sich ändern. "
                "Datei und RAM werden nach dem Neustart erneut verifiziert.\n\n"
                "Fortfahren?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return

        command = self._statistics_command(
            adb,
            "set-mainboard-ota-count",
            str(value),
            "--execute",
            "--confirm",
            CONFIRM_TOKEN,
            "--backup-dir",
            str(self._statistics_backup_dir()),
        )
        self._run(
            "statistics-set",
            command,
            str(operator.lte.desktop.app.base.backend_dir()),
        )

    @staticmethod
    def _last_event(output: str, wanted: str) -> dict | None:
        for line in reversed(output.splitlines()):
            try:
                record = json.loads(line)
            except Exception:
                continue
            if isinstance(record, dict) and record.get("event") == wanted:
                return record
        return None

    def _done(self, op, code, output):
        if op not in {"statistics-show", "statistics-set"}:
            super()._done(op, code, output)
            return

        # Reuse the normal process cleanup/button/log behavior, but do not let
        # the generic updater path interpret this independent maintenance run.
        super()._done("handled-result", code, output)

        if op == "statistics-show":
            result = self._last_event(output, "inspect")
            if result and isinstance(result.get("current_value"), int):
                value = int(result["current_value"])
                self.statistics_current.setText(f"Aktueller Wert: {value}")
                if result.get("ok") is True and code == 0:
                    self.statistics_current.setStyleSheet(
                        f"QLabel{{color:{operator.lte.desktop.app.GREEN};}}"
                    )
                else:
                    self.statistics_current.setStyleSheet(
                        f"QLabel{{color:{operator.lte.desktop.app.YELLOW};}}"
                    )
                return
            self.statistics_current.setStyleSheet(
                f"QLabel{{color:{operator.lte.desktop.app.RED};}}"
            )
            self.statistics_current.setText(
                "Aktueller Wert konnte nicht sicher geprüft werden – Details im Protokoll."
            )
            return

        complete = self._last_event(output, "complete")
        if code == 0 and complete:
            value = complete.get("value")
            backup = complete.get("backup")
            self.statistics_current.setStyleSheet(
                f"QLabel{{color:{operator.lte.desktop.app.GREEN};font-weight:bold;}}"
            )
            self.statistics_current.setText(f"Aktueller Wert: {value}")
            self.allow_statistics_write.setChecked(False)
            QMessageBox.information(
                self,
                "Mainboard OTA-Vorgänge geändert",
                "Der separate Maintenance-Core hat den Wert erfolgreich geändert.\n\n"
                f"Neuer Wert: {value}\n"
                "Persistente Datei: verifiziert\n"
                "RAM nach Neustart: verifiziert\n"
                f"Backup: {backup or 'siehe Protokoll'}",
            )
            if not self._modem_info_running:
                self._refresh_modem_info()
            return

        error = self._last_event(output, "error")
        message = (
            str(error.get("message"))
            if isinstance(error, dict) and error.get("message")
            else "Der Maintenance-Core hat den Vorgang nicht erfolgreich abgeschlossen."
        )
        QMessageBox.critical(
            self,
            "Wartung fehlgeschlagen",
            message + "\n\nDetails stehen im Protokoll.",
        )

    def _modem_info_result(self, value: object):
        super()._modem_info_result(value)
        if isinstance(value, PhnixModemInfo):
            count = value.statistics.mainboard_ota_count
            if count is not None and hasattr(self, "statistics_current"):
                self.statistics_current.setText(
                    f"Aktueller Wert: {count} (read-only Modem Info)"
                )
                self.statistics_current.setStyleSheet("")

    def _buttons(self):
        super()._buttons()
        if hasattr(self, "statistics_show_btn"):
            self.allow_statistics_write.setEnabled(not self.busy)
            self.statistics_target.setEnabled(not self.busy)
            self.statistics_show_btn.setEnabled(
                not self.busy and self._adb_ready()
            )
        if hasattr(self, "statistics_set_btn"):
            self.statistics_set_btn.setEnabled(
                not self.busy
                and self._adb_ready()
                and self.allow_statistics_write.isChecked()
                and self._statistics_value() is not None
            )
        if hasattr(self, "phnix_restart_btn"):
            self.phnix_restart_btn.setEnabled(not self.busy and self._adb_ready())


def main():
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("FoxAir Updater")
    qt_app.setOrganizationName("FoxAir")
    icon = operator.lte.desktop.app.base.root_dir() / "app_icon.ico"
    if icon.is_file():
        qt_app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
