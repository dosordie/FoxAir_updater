from __future__ import annotations

import os
import sys
import threading
from html import escape
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import foxair_updater_app as app
import phnix_windows_controller_wrapper as windows_wrapper
from updater.common.adb_transport import AdbClient
from updater.common.phnix_modem_info import PhnixModemInfo, format_seconds, read_phnix_modem_info


class ModemInfoSignals(QObject):
    result = Signal(object)
    error = Signal(str)


class MainWindow(app.MainWindow):
    """Current Windows desktop UI with read-only LTE diagnostics."""

    def __init__(self):
        self._modem_info_running = False
        self._modem_signals = ModemInfoSignals()
        self._modem_signals.result.connect(self._modem_info_result)
        self._modem_signals.error.connect(self._modem_info_error)
        super().__init__()
        self._refresh_block_state()

    def _ui(self):
        super()._ui()
        # Diagnostics are opt-in and sit immediately before Advanced.
        self.modem_tab_index = self.tabs.insertTab(
            5, self._modem_info_page(), "Modem Info / LTE Diagnose"
        )
        self.tabs.setTabVisible(self.modem_tab_index, True)

    def _advanced(self):
        widget = super()._advanced()
        layout = widget.layout()
        insert_at = max(0, layout.count() - 1)

        self.show_modem_diagnostics = QCheckBox("Modem-Diagnose / Traffic anzeigen")
        self.show_modem_diagnostics.setChecked(
            str(self.settings.value("show_modem_diagnostics", "false")).lower() in {"1", "true", "yes"}
        )
        self.show_modem_diagnostics.toggled.connect(self._toggle_modem_diagnostics)
        layout.insertWidget(insert_at, self.show_modem_diagnostics)
        insert_at += 1

        separator = QLabel("<hr><b>Lokalen Windows-Blockzustand zurücksetzen</b>")
        layout.insertWidget(insert_at, separator)
        insert_at += 1

        note = QLabel(
            "Für Recovery-/Testfälle kann ein offener <code>cache.pending</code>-Zustand "
            "nur nach eindeutig sicherer Controllerprüfung zurückgesetzt werden. Dabei wird "
            "die vorhandene Restore-/Konsistenzlogik des Update-Schutzes verwendet; bei einem unklaren "
            "oder möglicherweise bereits begonnenen Firmwaretransfer bleibt alles unverändert."
        )
        note.setWordWrap(True)
        layout.insertWidget(insert_at, note)
        insert_at += 1

        self.block_reset_status = QLabel()
        self.block_reset_status.setWordWrap(True)
        layout.insertWidget(insert_at, self.block_reset_status)
        insert_at += 1

        self.allow_block_reset = QCheckBox("Blockzustand zurücksetzen erlauben")
        self.allow_block_reset.toggled.connect(self._buttons)
        layout.insertWidget(insert_at, self.allow_block_reset)
        insert_at += 1

        self.block_reset_btn = QPushButton("cache.pending-Blockzustand zurücksetzen")
        self.block_reset_btn.clicked.connect(self._reset_block_pending)
        layout.insertWidget(insert_at, self.block_reset_btn)
        return widget

    def _toggle_modem_diagnostics(self, visible: bool) -> None:
        self.settings.setValue("show_modem_diagnostics", visible)
        self.settings.sync()
        if hasattr(self, "traffic_tab_index"):
            self.tabs.setTabVisible(self.traffic_tab_index, visible)

    def _modem_info_page(self):
        widget = QWidget()
        outer = QVBoxLayout(widget)

        note = QLabel(
            "<b>Read-only Diagnose des laufenden phnixIot4G-Prozesses.</b><br>"
            "Die Werte werden ausschließlich per ADB aus <code>/proc/&lt;PID&gt;/mem</code> "
            "gelesen. Diese Seite öffnet <b>nicht</b> <code>/dev/ttyHSL2</code>, sendet "
            "keine Modbus-/RS485-Telegramme und schreibt nicht in den Prozessspeicher."
        )
        note.setWordWrap(True)
        outer.addWidget(note)

        row = QHBoxLayout()
        self.modem_refresh_btn = QPushButton("Modem-Informationen neu lesen")
        self.modem_refresh_btn.clicked.connect(self._refresh_modem_info)
        row.addWidget(self.modem_refresh_btn)
        self.modem_read_status = QLabel("Noch nicht gelesen.")
        self.modem_read_status.setWordWrap(True)
        row.addWidget(self.modem_read_status, 1)
        outer.addLayout(row)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        self.modem_info_text = QLabel(
            '<span style="color:#667085;">Noch keine Modem-Diagnosedaten gelesen.</span>'
        )
        self.modem_info_text.setWordWrap(True)
        self.modem_info_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.modem_info_text.setStyleSheet(
            "QLabel{background:#f7f8fa;border:1px solid #d0d5dd;padding:10px;}"
        )
        content_layout.addWidget(self.modem_info_text)
        content_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        return widget

    @staticmethod
    def _wrapper_pending_path() -> Path:
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return (
            base
            / "FoxAir Updater"
            / "windows-wrapper-state"
            / "original-cache"
            / "cache.pending"
        )

    def _refresh_block_state(self):
        if not hasattr(self, "block_reset_status"):
            return
        marker = self._wrapper_pending_path()
        if marker.exists():
            self.block_reset_status.setStyleSheet(f"QLabel{{color:{app.YELLOW};font-weight:bold;}}")
            self.block_reset_status.setText(
                "Lokaler Blockzustand ist aktiv:<br><code>" + escape(str(marker)) + "</code>"
            )
        else:
            self.block_reset_status.setStyleSheet(f"QLabel{{color:{app.GREEN};}}")
            self.block_reset_status.setText("Kein lokaler cache.pending-Blockzustand vorhanden.")
        self._buttons()

    def _reset_block_pending(self, checked: bool = False, *, from_dry_run: bool = False):
        if self.busy or (not from_dry_run and not self.allow_block_reset.isChecked()):
            return
        marker = self._wrapper_pending_path()
        if not marker.exists():
            self._refresh_block_state()
            QMessageBox.information(self, "Blockzustand", "cache.pending ist bereits nicht vorhanden.")
            return

        run_state = self._latest_controller_run_state()
        simulator_state = self._stopped_simulator_state()
        if not windows_wrapper.dirty_state_reset_is_safe(run_state, simulator_state):
            QMessageBox.warning(
                self,
                "Sicherheitszustand nicht zurücksetzbar",
                "Ein kritischer Firmwaretransfer kann anhand des Controller-Run-State nicht sicher "
                "ausgeschlossen werden. Der Zustand bleibt unverändert.",
            )
            return
        if (
            QMessageBox.warning(
                self,
                "Offenen Sicherheitszustand sicher zurücksetzen?",
                "Es wurde ein offener Sicherheitszustand eines vorherigen Laufs gefunden. "
                "Dies kann von einem nicht sauber beendeten Lauf stammen.\n\n"
                "Der Controller bestätigt einen Zustand vor dem Firmwaretransfer. Die vorhandene "
                "Restore- und Konsistenzprüfung des Update-Schutzes wird jetzt verwendet; Marker werden nicht "
                "blind gelöscht.\n\nSicherheitszustand sicher zurücksetzen?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return

        self.allow_block_reset.setChecked(False)
        self._backend("restore", ["run", "--restore", "original"])

    def _latest_controller_run_state(self) -> dict | None:
        candidates = [path for path in self.state_dir.glob("*/run-state.json") if path.is_file()]
        if not candidates:
            return None
        try:
            value = __import__("json").loads(
                max(candidates, key=lambda path: path.stat().st_mtime_ns).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def _stopped_simulator_state(self) -> dict | None:
        adb = self._adb_path()
        if adb is None:
            return None
        try:
            client = AdbClient(adb, env=self._process_env())
            is_simulator = client.shell("test -f /data/.phnix_ota_simulator; echo $?") == "0"
            first_status = client.shell("cat /tmp/phnix_ota_status.json")
            running = client.shell("test -f /tmp/phnix_ota_hook/run.active; echo $?") == "0"
            second_status = client.shell("cat /tmp/phnix_ota_status.json")
            if not is_simulator or first_status != second_status:
                return None
            status = __import__("json").loads(second_status)
        except (OSError, RuntimeError, ValueError):
            return None
        return {
            "marker": "PHNIX-OTA-SIMULATOR-V1",
            "status": status,
            "runtime": {"running": running},
        }

    def _dry(self):
        if self._wrapper_pending_path().exists():
            self._reset_block_pending(from_dry_run=True)
            return
        super()._dry()

    def _refresh_modem_info(self):
        if self.busy or self._modem_info_running:
            return
        adb = self._require_adb()
        if not adb:
            return

        self._modem_info_running = True
        self.modem_read_status.setStyleSheet("")
        self.modem_read_status.setText("Lese phnixIot4G-Prozessspeicher …")
        self._buttons()

        def work():
            try:
                client = AdbClient(adb, env=self._process_env())
                value = read_phnix_modem_info(client)
            except Exception as error:
                self._modem_signals.error.emit(str(error))
            else:
                self._modem_signals.result.emit(value)

        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _fmt(value) -> str:
        if value is None or value == "":
            return '<span style="color:#667085;">nicht verfügbar</span>'
        return escape(str(value))

    @staticmethod
    def _fmt_count(value: int | None) -> str:
        if value is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        return f"{value:,}".replace(",", ".")

    def _modem_info_html(self, info: PhnixModemInfo) -> str:
        stats = info.statistics
        avg = stats.average_csq
        avg_text = "nicht verfügbar" if avg is None else f"{avg:.2f}"

        if info.rs485_ok is True:
            rs485 = f'<span style="color:{app.GREEN};"><b>OK</b> – keine bekannten RS485/Mainboard-Fehlerbits gesetzt</span>'
        elif info.rs485_ok is False:
            rs485 = f'<span style="color:{app.RED};"><b>Fehler gemeldet</b></span>'
        else:
            rs485 = '<span style="color:#667085;">nicht verfügbar</span>'

        if info.cloud_error is True:
            cloud = f'<span style="color:{app.RED};"><b>Fehlerbit gesetzt</b></span>'
        elif info.cloud_error is False:
            cloud = f'<span style="color:{app.GREEN};">kein bekannter Cloud-Fehler in ErrorStatue gesetzt</span>'
        else:
            cloud = '<span style="color:#667085;">nicht verfügbar</span>'

        error_bitmap = (
            f"0x{info.error_status:08X}" if info.error_status is not None else "nicht verfügbar"
        )
        errors = info.error_messages
        error_text = "<br>".join("• " + escape(item) for item in errors) if errors else "keine bekannten Fehlerbits gesetzt"

        id_note = "nicht verfügbar – stabile Zuordnung im Binary noch offen"
        if stats.unverified_device_id_candidate:
            id_note += " (ein unbestätigter ASCII-Kandidat ist vorhanden und wird bewusst nicht als ID ausgegeben)"

        rows = [
            "<h3>Mainboard</h3>",
            f"Firmwareversion: <b>{self._fmt(info.firmware_version)}</b><br>",
            f"Softwarecode: <b>{self._fmt(info.software_code)}</b><br>",
            f"Hardwarecode: <b>{self._fmt(info.hardware_code)}</b><br>",
            f"Hardwareversion: <b>{self._fmt(info.hardware_version)}</b><br>",
            "<h3>LTE / Modem</h3>",
            f"Aktueller CSQ: <b>{self._fmt(stats.current_csq)}</b><br>",
            f"Durchschnitts-CSQ (Summe/Samples): <b>{self._fmt(avg_text if avg is not None else None)}</b><br>",
            f"Stärkster CSQ: <b>{self._fmt(stats.strongest_csq)}</b><br>",
            f"Schwächster CSQ: <b>{self._fmt(stats.weakest_csq)}</b><br>",
            f"Device-/DTU-ID: <span style=\"color:#667085;\">{escape(id_note)}</span><br>",
            "<h3>Verbindung / Fehler</h3>",
            f"Mainboard / RS485: {rs485}<br>",
            f"Cloudstatus: {cloud}<br>",
            f"ErrorStatue Bitmap: <code>{escape(error_bitmap)}</code><br>",
            f"Fehlertexte:<br>{error_text}<br>",
            "<h3>Statistik</h3>",
            f"Gesamtbetriebszeit: <b>{escape(format_seconds(stats.work_time))}</b><br>",
            f"Gesamt-Onlinezeit: <b>{escape(format_seconds(stats.online_time))}</b><br>",
            f"Aktuelle Laufzeit: <b>{escape(format_seconds(stats.current_work_time))}</b><br>",
            f"Aktuelle Onlinezeit: <b>{escape(format_seconds(stats.current_online_time))}</b><br>",
            f"Uploadzähler: <b>{self._fmt_count(stats.upload_count)}</b><br>",
            f"Downloadzähler: <b>{self._fmt_count(stats.download_count)}</b><br>",
            f"DTU-OTA-Zähler: <b>{self._fmt_count(stats.dtu_ota_count)}</b><br>",
            f"Mainboard-OTA-Zähler: <b>{self._fmt_count(stats.mainboard_ota_count)}</b><br>",
            f"Power-Reset-Zähler: <b>{self._fmt_count(stats.power_reset_count)}</b><br>",
            f"Active-/Software-Reset-Zähler: <b>{self._fmt_count(stats.active_reset_count)}</b><br>",
        ]

        if info.read_errors:
            rows.extend(
                [
                    "<h3>Hinweise zu unvollständigen Reads</h3>",
                    '<span style="color:#b26a00;">'
                    + "<br>".join("• " + escape(item) for item in info.read_errors)
                    + "</span>",
                ]
            )
        return "".join(rows)

    def _modem_info_result(self, value: object):
        self._modem_info_running = False
        if not isinstance(value, PhnixModemInfo):
            self._modem_info_error("Unerwarteter Modem-Info-Datentyp")
            return

        self.modem_info_text.setText(self._modem_info_html(value))
        if value.pid is None:
            self.modem_read_status.setStyleSheet(f"QLabel{{color:{app.RED};}}")
            self.modem_read_status.setText("phnixIot4G nicht lesbar – Werte nicht verfügbar.")
        elif value.read_errors:
            self.modem_read_status.setStyleSheet(f"QLabel{{color:{app.YELLOW};}}")
            self.modem_read_status.setText(
                f"PID {value.pid} gelesen – einzelne Werte sind nicht verfügbar."
            )
        else:
            self.modem_read_status.setStyleSheet(f"QLabel{{color:{app.GREEN};}}")
            self.modem_read_status.setText(f"PID {value.pid} – read-only Diagnose erfolgreich gelesen.")
        self._buttons()

    def _modem_info_error(self, message: str):
        self._modem_info_running = False
        self.modem_read_status.setStyleSheet(f"QLabel{{color:{app.RED};}}")
        self.modem_read_status.setText("Modem-Diagnose konnte nicht gelesen werden.")
        self.modem_info_text.setText(
            '<span style="color:#b42318;">' + escape(message) + "</span>"
        )
        self._log("[Modem Info] " + message)
        self._buttons()

    def _resolve_flow_step(self, key: str, text: str):
        if key in self._flow_steps:
            self._set_step(key, "ok", text)

    def _handle_phase(self, phase: str):
        super()._handle_phase(phase)

        # The previous GUI left historical in-progress phases yellow for the
        # whole update.  Once a later phase proves they completed, turn those
        # entries green.  Only the currently active phase stays yellow/orange.
        if phase in {"accepted", "c350-sent", "c350", "c357", "c5a8", "success-report", "success"}:
            self._resolve_flow_step("hook-start", "Updateablauf wurde gestartet und die Mainboard-Reaktion wird überwacht.")
            self._resolve_flow_step("phase-yield", "Sicherer Sendepunkt im Originaldienst wurde erreicht.")
            self._resolve_flow_step("phase-start", "Updateauftrag wurde kontrolliert an den Originaldienst übergeben.")
        if phase in {"c357", "c5a8", "success-report", "success"}:
            self._resolve_flow_step("phase-c350", "Mainboard hat Firmwarekennung und Version geprüft.")
        if phase in {"success-report", "success"}:
            self._resolve_flow_step("phase-c5a8", "Firmwaredaten wurden vollständig zum Mainboard übertragen.")

    def _handle_record(self, record: dict):
        super()._handle_record(record)
        if record.get("event") == "complete":
            self._resolve_flow_step("phase-c5a8", "Firmwaredaten wurden vollständig zum Mainboard übertragen.")

    def _buttons(self):
        super()._buttons()
        if hasattr(self, "modem_refresh_btn"):
            self.modem_refresh_btn.setEnabled(
                not self.busy and not self._modem_info_running and self._adb_ready()
            )
        if hasattr(self, "block_reset_btn"):
            self.allow_block_reset.setEnabled(not self.busy)
            self.block_reset_btn.setEnabled(
                not self.busy
                and self.allow_block_reset.isChecked()
                and self._wrapper_pending_path().exists()
            )


def main():
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("FoxAir Updater")
    qt_app.setOrganizationName("FoxAir")
    icon = app.base.root_dir() / "app_icon.ico"
    if icon.is_file():
        qt_app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
