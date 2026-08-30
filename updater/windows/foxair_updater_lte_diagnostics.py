from __future__ import annotations

import sys
import threading
from datetime import datetime
from html import escape
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QFileDialog,
    QLabel,
    QComboBox,
    QDialog,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import foxair_updater_desktop as desktop
from updater.common.adb_transport import AdbClient
from updater.common.phnix_modem_info import PhnixModemInfo, format_seconds, read_phnix_modem_info
from updater.common.phnix_debug import (
    PhnixDebugCapture,
    TcpDebugSource,
    explain_debug_line,
    remote_debug_endpoint,
    resolve_phnix_debug_port,
)


class DebugSignals(QObject):
    line = Signal(str, object)
    update_line = Signal(str, object)


class QtSerialDebugSource:
    """Blocking, read-only QtSerialPort adapter, constructed in the reader thread."""
    def __init__(self, port: str):
        from PySide6.QtSerialPort import QSerialPort
        self.description = f"Lokal: {port} / MI_04"
        self._serial = QSerialPort()
        self._serial.setPortName(port)
        self._serial.setBaudRate(115200)
        self._serial.setDataBits(QSerialPort.Data8)
        self._serial.setParity(QSerialPort.NoParity)
        self._serial.setStopBits(QSerialPort.OneStop)
        self._serial.setFlowControl(QSerialPort.NoFlowControl)
        if not self._serial.open(QSerialPort.ReadOnly):
            raise OSError(self._serial.errorString())

    def read(self, size: int) -> bytes:
        self._serial.waitForReadyRead(500)
        return bytes(self._serial.read(size))

    def close(self) -> None:
        self._serial.close()


class PhnixDebugWindow(QDialog):
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PHNIX Debugmonitor (nur Lesen)")
        self.resize(900, 560)
        layout = QVBoxLayout(self)
        self.status = QLabel("Nicht verfügbar")
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(("Original", "Original + deutsche Erläuterungen"))
        self.autoscroll = QCheckBox("Auto-Scroll")
        self.autoscroll.setChecked(True)
        clear = QPushButton("Anzeige leeren")
        clear.clicked.connect(lambda: self.output.clear())
        save = QPushButton("Log speichern…")
        save.clicked.connect(self._save)
        row.addWidget(self.mode)
        row.addWidget(self.autoscroll)
        row.addStretch()
        row.addWidget(clear)
        row.addWidget(save)
        layout.addLayout(row)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)

    def append_line(self, line: str) -> None:
        self.output.appendPlainText(explain_debug_line(line) if self.mode.currentIndex() else line)
        if self.autoscroll.isChecked():
            self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum())

    def _save(self):
        name, _ = QFileDialog.getSaveFileName(self, "PHNIX-Debuglog speichern", "PHNIX_Debug.log", "Log (*.log)")
        if name:
            Path(name).write_text(self.output.toPlainText() + "\n", encoding="utf-8")

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)


class MainWindow(desktop.MainWindow):
    """Desktop GUI extension for read-only LTE/SIM/cloud diagnostics."""

    def __init__(self):
        self._last_modem_info: PhnixModemInfo | None = None
        self._debug_signals = DebugSignals()
        self._debug_signals.line.connect(self._debug_line)
        self._debug_signals.update_line.connect(self._update_debug_line)
        self._debug_capture: PhnixDebugCapture | None = None
        self._debug_window: PhnixDebugWindow | None = None
        self._automatic_log = None
        self._lte_log = None
        super().__init__()

    def _modem_info_page(self):
        widget = QWidget()
        outer = QVBoxLayout(widget)

        note = QLabel(
            "<b>Read-only Diagnose des laufenden phnixIot4G-Prozesses und des Linux-Netzwerks.</b><br>"
            "RAM-Werte werden ausschließlich per ADB aus <code>/proc/&lt;PID&gt;/mem</code> gelesen. "
            "Die Seite öffnet <b>nicht</b> <code>/dev/ttyHSL2</code>, sendet keine zusätzlichen "
            "Modbus-/RS485-Telegramme und schreibt nicht in den Prozessspeicher. "
            "Mobilfunk-IP und Gateway stammen read-only aus Linux-Netzwerkdaten."
        )
        note.setWordWrap(True)
        outer.addWidget(note)

        row = QHBoxLayout()
        self.modem_refresh_btn = desktop.QPushButton("Modem-Informationen neu lesen")
        self.modem_refresh_btn.clicked.connect(self._refresh_modem_info)
        row.addWidget(self.modem_refresh_btn)
        self.modem_read_status = QLabel("Noch nicht gelesen.")
        self.modem_read_status.setWordWrap(True)
        row.addWidget(self.modem_read_status, 1)
        outer.addLayout(row)

        debug_row = QHBoxLayout()
        self.debug_monitor_btn = desktop.QPushButton("PHNIX Debugmonitor öffnen")
        self.debug_monitor_btn.clicked.connect(self._open_debug_monitor)
        debug_row.addWidget(self.debug_monitor_btn)
        debug_row.addWidget(QLabel("ttyGS0 / USB MI_04 – ausschließlich read-only"))
        debug_row.addStretch()
        outer.addLayout(debug_row)

        self.show_cloud_secrets = QCheckBox("Cloud-Secrets anzeigen")
        self.show_cloud_secrets.setToolTip(
            "Secrets werden nur in dieser Ansicht eingeblendet und nicht automatisch protokolliert."
        )
        self.show_cloud_secrets.toggled.connect(self._rerender_modem_info)
        outer.addWidget(self.show_cloud_secrets)

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

    def _new_debug_capture(self) -> PhnixDebugCapture:
        if self.adb_remote.isChecked():
            host, port = remote_debug_endpoint(self.remote_host.text(), self.remote_port.value())
            return PhnixDebugCapture(lambda: TcpDebugSource(host, port))
        port = resolve_phnix_debug_port()
        if not port:
            return PhnixDebugCapture(lambda: (_ for _ in ()).throw(OSError("MI_04 nicht eindeutig gefunden")))
        return PhnixDebugCapture(lambda: QtSerialDebugSource(port))

    def _ensure_debug_capture(self) -> PhnixDebugCapture:
        if self._debug_capture is None:
            self._debug_capture = self._new_debug_capture()
        return self._debug_capture

    def _open_debug_monitor(self):
        if self._debug_window is None:
            self._debug_window = PhnixDebugWindow(self)
            self._debug_window.closed.connect(self._close_debug_monitor)
            capture = self._ensure_debug_capture()
            opened = capture.add_consumer("window", lambda line, event: self._debug_signals.line.emit(line, event))
            self._debug_window.status.setText(capture.status)
            if not opened:
                self._log("[Warnung] PHNIX LTE-Debugport nicht verfügbar – Diagnose bleibt ohne Stream.")
        self._debug_window.show()
        self._debug_window.raise_()

    def _close_debug_monitor(self):
        if self._debug_capture:
            self._debug_capture.remove_consumer("window")
        self._debug_window = None

    def _debug_line(self, line: str, event: object):
        if self._debug_window:
            self._debug_window.append_line(line)

    def _update_debug_line(self, line: str, event: object):
        if self._lte_log:
            try:
                self._lte_log.write(explain_debug_line(line) + "\n")
                self._lte_log.flush()
            except OSError as error:
                self._lte_log = None
                self._log(f"[Warnung] Automatisches LTE-Log konnte nicht weitergeschrieben werden: {error}")
        # Supplementary progress is shown only once the controller has authoritatively entered C5A8.
        if getattr(event, "kind", None) == "transfer-progress" and "phase-c5a8" in self._flow_steps:
            percent = event.progress
            self.progress_text.setText(
                f"Firmwaredaten werden an das Mainboard übertragen – PHNIX: {percent:.1f} % / "
                f"{event.current} von {event.total} Byte"
            )
        self._apply_debug_event(event)

    def _update_existing_debug_step(self, key: str, level: str, text: str) -> None:
        """Refine a visible controller step without creating a new safety fact."""
        if key in self._flow_steps:
            self._set_step(key, level, text)

    def _apply_debug_event(self, event: object) -> None:
        kind = getattr(event, "kind", None)
        if kind == "transfer-complete":
            self._update_existing_debug_step(
                "phase-c5a8", "warn",
                "Firmwaredaten vollständig an das Mainboard übertragen – Mainboard verarbeitet das Image; Controllerprüfung läuft.",
            )
        elif kind == "manufacturer-success":
            self._update_existing_debug_step(
                "phase-c5a8", "warn",
                "PHNIX-Originaldienst meldet Mainboard-Update erfolgreich – abschließende Controllerprüfung läuft.",
            )
        elif kind == "mqtt-normal":
            self._update_existing_debug_step(
                "preflight-mqtt", "ok",
                "PHNIX-Originaldienst meldet Aliyun/MQTT als verbunden.",
            )
        elif kind == "cloud-progress":
            progress = int(event.progress)
            if event.code == "0043":
                self._update_existing_debug_step(
                    "phase-c5a8", "warn",
                    f"Firmwaredaten werden an das Mainboard übertragen – PHNIX-Cloudfortschritt {progress} %; Controller bleibt maßgeblich.",
                )
            elif event.code == "0053":
                self._update_existing_debug_step(
                    "phase-success-report", "warn",
                    f"PHNIX-Originaldienst meldet Mainboard-OTA-Status {progress} % – abschließende Controllerprüfung läuft.",
                )

    def _start_automatic_logs(self, manifest: Path) -> None:
        self._finish_automatic_logs()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        directory = manifest.parent
        try:
            self._automatic_log = (directory / f"FoxAir_Update_{stamp}.log").open("a", encoding="utf-8")
            self._lte_log = (directory / f"FoxAir_Update_{stamp}_LTE.log").open("a", encoding="utf-8")
        except OSError as error:
            for stream in (self._automatic_log, self._lte_log):
                if stream:
                    stream.close()
            self._automatic_log = self._lte_log = None
            self._log(f"[Warnung] Automatische Update-Logs konnten nicht angelegt werden: {error}")
        capture = self._ensure_debug_capture()
        if not capture.add_consumer(
            "update", lambda line, event: self._debug_signals.update_line.emit(line, event)
        ):
            warning = (
                "Remote PHNIX-Debugstream nicht erreichbar – Fortsetzung ohne LTE-Debug."
                if self.adb_remote.isChecked() else
                "PHNIX LTE-Debugport nicht verfügbar – Update wird ohne LTE-Debuglog fortgesetzt."
            )
            self._log("[Warnung] " + warning)

    def _finish_automatic_logs(self) -> None:
        if self._debug_capture:
            self._debug_capture.remove_consumer("update")
        for stream_name in ("_automatic_log", "_lte_log"):
            stream = getattr(self, stream_name, None)
            if stream:
                try:
                    stream.close()
                except OSError:
                    pass
            setattr(self, stream_name, None)

    def _run(self, op, command, cwd=None):
        if op in {"dry", "update"}:
            try:
                index = command.index("--manifest")
                manifest = Path(command[index + 1])
            except (ValueError, IndexError):
                manifest = None
            if manifest and manifest.is_file():
                self._start_automatic_logs(manifest)
        super()._run(op, command, cwd)

    def _done(self, op, code, output):
        super()._done(op, code, output)
        if op in {"dry", "update"}:
            QTimer.singleShot(1200, self._finish_automatic_logs)

    def _log(self, text):
        super()._log(text)
        if self._automatic_log:
            try:
                self._automatic_log.write(text + "\n")
                self._automatic_log.flush()
            except OSError as error:
                self._automatic_log = None
                super()._log(f"[Warnung] Automatisches Controller-Log konnte nicht weitergeschrieben werden: {error}")

    def _refresh_modem_info(self):
        if self.busy or self._modem_info_running:
            return
        adb = self._require_adb()
        if not adb:
            return

        self._modem_info_running = True
        self.modem_read_status.setStyleSheet("")
        self.modem_read_status.setText("Lese read-only Modem-, SIM-, Mobilfunk- und Cloudinformationen …")
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

    @staticmethod
    def _known_one(value: int | None, yes_text: str = "Ja") -> str:
        if value is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        if value == 1:
            return yes_text
        return f"unbekannt ({value})"

    @staticmethod
    def _sim_state(value: int | None) -> str:
        if value is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        if value == 7:
            return "READY"
        return f"unbekannt ({value})"

    @staticmethod
    def _rat(value: int | None) -> str:
        if value is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        if value == 8:
            return "LTE"
        return f"unbekannt ({value})"

    @staticmethod
    def _csq(value: int | float | None, *, decimals: int = 0) -> str:
        if value is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        numeric = float(value)
        text = f"{numeric:.{decimals}f}" if decimals else str(int(numeric))
        if 0 <= numeric <= 31:
            return f"{text} / 31"
        return f"{text} (Rohwert außerhalb 0…31)"

    @staticmethod
    def _roaming(info: PhnixModemInfo) -> str:
        if info.roaming_valid != 1:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        mapping = {0: "Ja", 1: "Nein", 2: "FLASHING"}
        if info.roaming_indicator is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        return mapping.get(info.roaming_indicator, f"unbekannt ({info.roaming_indicator})")

    @staticmethod
    def _plmn(info: PhnixModemInfo) -> str:
        if info.current_plmn_valid != 1 or info.mcc is None or info.mnc is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        return f"{info.mcc:03d} / {info.mnc:02d}"

    @staticmethod
    def _lac(info: PhnixModemInfo) -> str:
        if info.lac is None or info.lac == 0xFFFE:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        return str(info.lac)

    def _secret(self, value: str | None) -> str:
        if not value:
            return '<span style="color:#667085;">nicht geladen</span>'
        if self.show_cloud_secrets.isChecked():
            return f"<code>{escape(value)}</code>"
        return "<code>••••••••••••••••</code>"

    @staticmethod
    def _mqtt(info: PhnixModemInfo) -> str:
        cloud = info.cloud
        if cloud.pclient_pointer is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        if cloud.pclient_pointer == 0:
            return '<span style="color:#667085;">Nicht initialisiert</span>'
        if cloud.mqtt_state == 2:
            return f'<span style="color:{desktop.app.GREEN};"><b>Verbunden</b></span>'
        if cloud.mqtt_state is None:
            return '<span style="color:#667085;">Status nicht verfügbar</span>'
        return (
            f'<span style="color:{desktop.app.YELLOW};">Nicht verbunden / Verbindungsaufbau '
            f"(State {cloud.mqtt_state})</span>"
        )

    def _modem_info_html(self, info: PhnixModemInfo) -> str:
        stats = info.statistics
        avg = stats.average_csq

        if info.rs485_ok is True:
            rs485 = (
                f'<span style="color:{desktop.app.GREEN};"><b>OK</b> – keine bekannten '
                "RS485/Mainboard-Fehlerbits gesetzt</span>"
            )
        elif info.rs485_ok is False:
            rs485 = f'<span style="color:{desktop.app.RED};"><b>Fehler gemeldet</b></span>'
        else:
            rs485 = '<span style="color:#667085;">nicht verfügbar</span>'

        if info.cloud_error is True:
            error_cloud = f'<span style="color:{desktop.app.RED};"><b>Fehlerbit gesetzt</b></span>'
        elif info.cloud_error is False:
            error_cloud = (
                f'<span style="color:{desktop.app.GREEN};">kein bekannter Cloud-Fehler '
                "in ErrorStatue gesetzt</span>"
            )
        else:
            error_cloud = '<span style="color:#667085;">nicht verfügbar</span>'

        error_bitmap = (
            f"0x{info.error_status:08X}" if info.error_status is not None else "nicht verfügbar"
        )
        errors = info.error_messages
        error_text = (
            "<br>".join("• " + escape(item) for item in errors)
            if errors
            else "keine bekannten Fehlerbits gesetzt"
        )

        rows = [
            "<h3>Mainboard</h3>",
            f"Firmware: <b>{self._fmt(info.firmware_version)}</b><br>",
            f"Softwarecode: <b>{self._fmt(info.software_code)}</b><br>",
            f"Hardwarecode: <b>{self._fmt(info.hardware_code)}</b><br>",
            f"Hardwareversion: <b>{self._fmt(info.hardware_version)}</b><br>",
            "<h3>Modem</h3>",
            f"Modell: <b>{self._fmt(info.modem_model)}</b><br>",
            f"IMEI: <b>{self._fmt(info.imei)}</b><br>",
            "<h3>SIM</h3>",
            f"ICCID: <b>{self._fmt(info.iccid)}</b><br>",
            f"IMSI: <b>{self._fmt(info.imsi)}</b><br>",
            f"SIM vorhanden: <b>{self._known_one(info.sim.card_status)}</b><br>",
            f"SIM Status: <b>{self._sim_state(info.sim.app_state)}</b><br>",
            f"SIM App-Type (roh): <b>{self._fmt(info.sim.app_type)}</b><br>",
            "<h3>Mobilfunk</h3>",
            f"Mobilfunkstandard: <b>{self._rat(info.serving.radio_interface_0)}</b><br>",
            f"Registriert: <b>{self._known_one(info.serving.registration_state)}</b><br>",
            f"CS Attach: <b>{self._known_one(info.serving.cs_attach_state)}</b><br>",
            f"PS Attach: <b>{self._known_one(info.serving.ps_attach_state)}</b><br>",
            f"Netzkennung MCC / MNC: <b>{self._plmn(info)}</b><br>",
            f"Netzbeschreibung: <b>{self._fmt(info.network_description if info.current_plmn_valid == 1 else None)}</b><br>",
            f"Roaming: <b>{self._roaming(info)}</b><br>",
            f"Cell-ID: <b>{self._fmt(info.cell_id)}</b><br>",
            f"LAC/TAC: <b>{self._lac(info)}</b><br>",
            f"Signal aktuell: <b>{self._csq(stats.current_csq)}</b><br>",
            f"Signal Ø: <b>{self._csq(avg, decimals=1)}</b><br>",
            f"Signal Maximum: <b>{self._csq(stats.strongest_csq)}</b><br>",
            f"Signal Minimum: <b>{self._csq(stats.weakest_csq)}</b><br>",
            "<h3>Netzwerk</h3>",
            f"Mobilfunkinterface: <b>{self._fmt(info.network.interface)}</b><br>",
            f"Mobilfunk-IP / PDP-IP: <b>{self._fmt(info.network.ip_address)}</b><br>",
            f"Präfix: <b>{('/' + str(info.network.prefix_length)) if info.network.prefix_length is not None else self._fmt(None)}</b><br>",
            f"Gateway: <b>{self._fmt(info.network.gateway)}</b><br>",
            "<h3>Cloud</h3>",
            f"MQTT / Cloud: {self._mqtt(info)}<br>",
            f"Aliyun DeviceName: <b>{self._fmt(info.cloud.device_name)}</b><br>",
            f"ProductKey: <b>{self._fmt(info.cloud.product_key)}</b><br>",
            f"DeviceSecret: {self._secret(info.cloud.device_secret)}<br>",
            f"ProductSecret: {self._secret(info.cloud.product_secret)}<br>",
            f"MQTT State (roh): <b>{self._fmt(info.cloud.mqtt_state)}</b><br>",
            f"MQTT_init_signal (diagnostisch): <b>{self._fmt(info.cloud.mqtt_init_signal)}</b><br>",
            "<h3>Statistik / Fehler</h3>",
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
            f"Mainboard / RS485: {rs485}<br>",
            f"Cloud-Fehlerbits: {error_cloud}<br>",
            f"ErrorStatue Bitmap: <code>{escape(error_bitmap)}</code><br>",
            f"Fehlertexte:<br>{error_text}<br>",
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

    def _rerender_modem_info(self):
        if self._last_modem_info is not None:
            self.modem_info_text.setText(self._modem_info_html(self._last_modem_info))

    def _modem_info_result(self, value: object):
        self._modem_info_running = False
        if not isinstance(value, PhnixModemInfo):
            self._modem_info_error("Unerwarteter Modem-Info-Datentyp")
            return

        self._last_modem_info = value
        self.modem_info_text.setText(self._modem_info_html(value))
        if value.pid is None:
            self.modem_read_status.setStyleSheet(f"QLabel{{color:{desktop.app.RED};}}")
            self.modem_read_status.setText("phnixIot4G nicht lesbar – Werte nicht verfügbar.")
        elif value.read_errors:
            self.modem_read_status.setStyleSheet(f"QLabel{{color:{desktop.app.YELLOW};}}")
            self.modem_read_status.setText(
                f"PID {value.pid} gelesen – einzelne Werte sind nicht verfügbar."
            )
        else:
            self.modem_read_status.setStyleSheet(f"QLabel{{color:{desktop.app.GREEN};}}")
            self.modem_read_status.setText(
                f"PID {value.pid} – read-only Diagnose erfolgreich gelesen."
            )
        self._buttons()

    def _modem_info_error(self, message: str):
        self._modem_info_running = False
        self._last_modem_info = None
        self.modem_read_status.setStyleSheet(f"QLabel{{color:{desktop.app.RED};}}")
        self.modem_read_status.setText("Modem-Diagnose konnte nicht gelesen werden.")
        self.modem_info_text.setText(
            '<span style="color:#b42318;">' + escape(message) + "</span>"
        )
        # Error messages never contain decoded secret values.  Normal modem
        # diagnostic values are intentionally not copied into the application log.
        self._log("[Modem Info] " + message)
        self._buttons()


def main():
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("FoxAir Updater")
    qt_app.setOrganizationName("FoxAir")
    icon = desktop.app.base.root_dir() / "app_icon.ico"
    if icon.is_file():
        qt_app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
