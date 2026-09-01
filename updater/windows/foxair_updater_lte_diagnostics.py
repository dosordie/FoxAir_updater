from __future__ import annotations

import json
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
from updater.common.phnix_service_restart import (
    restart_phnix_iot_service,
    wait_for_phnix_runtime_ready,
)
from updater.common.phnix_debug import (
    PhnixDebugCapture,
    SerialCompletionSequence,
    TcpDebugSource,
    completion_events_for_line,
    explain_debug_line,
    remote_debug_endpoint,
    resolve_phnix_debug_port,
)


class DebugSignals(QObject):
    line = Signal(str, object)
    update_line = Signal(int, str, object)
    status = Signal(str, object)


class PreUpdateRestartSignals(QObject):
    done = Signal(bool, str)


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
        from PySide6.QtSerialPort import QSerialPort
        ready = self._serial.waitForReadyRead(500)
        if not ready and self._serial.error() not in (QSerialPort.NoError, QSerialPort.TimeoutError):
            raise OSError(self._serial.errorString())
        return bytes(self._serial.read(size))

    def close(self) -> None:
        self._serial.close()


class PhnixDebugWindow(QDialog):
    closed = Signal()
    connect_requested = Signal()
    disconnect_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PHNIX Debugmonitor (nur Lesen)")
        self.resize(900, 560)
        layout = QVBoxLayout(self)
        self.status = QLabel("Status: Getrennt")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(("Original", "Original + deutsche Erläuterungen"))
        self.mode.setCurrentIndex(1)
        self.connect_btn = QPushButton("Verbinden")
        self.connect_btn.clicked.connect(self.connect_requested)
        self.disconnect_btn = QPushButton("Trennen")
        self.disconnect_btn.clicked.connect(self.disconnect_requested)
        self.autoscroll = QCheckBox("Auto-Scroll")
        self.autoscroll.setChecked(True)
        clear = QPushButton("Anzeige leeren")
        clear.clicked.connect(lambda: self.output.clear())
        save = QPushButton("Log speichern…")
        save.clicked.connect(self._save)
        row.addWidget(self.mode)
        row.addWidget(self.connect_btn)
        row.addWidget(self.disconnect_btn)
        row.addWidget(self.autoscroll)
        row.addStretch()
        row.addWidget(clear)
        row.addWidget(save)
        layout.addLayout(row)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(10000)
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
        self._debug_signals.update_line.connect(self._update_debug_line_for_run)
        self._debug_signals.status.connect(self._debug_status)
        self._pre_update_restart_signals = PreUpdateRestartSignals()
        self._pre_update_restart_signals.done.connect(self._pre_update_restart_finished)
        self._pending_update_start = None
        self._debug_capture: PhnixDebugCapture | None = None
        self._debug_window: PhnixDebugWindow | None = None
        self._automatic_log = None
        self._lte_log = None
        self._debug_connected_since: datetime | None = None
        self._debug_last_data: datetime | None = None
        self._last_debug_status = "Getrennt"
        self._debug_source_description = "Quelle: Lokal\nEndpunkt: MI_04"
        self._debug_open_warning_shown = False
        self._phnix_transfer_event = None
        self._update_run_generation = 0
        self._serial_sequence: SerialCompletionSequence | None = None
        self._serial_c5a8_started = False
        self._serial_transfer_started = False
        self._serial_monitoring_lost = False
        self._serial_fallback_success = False
        self._serial_capture_identity: str | None = None
        self._serial_success_tail_generation: int | None = None
        self._serial_reattach_pending_generation: int | None = None
        self._serial_reattach_started_generation: int | None = None
        super().__init__()
        self._debug_status_timer = QTimer(self)
        self._debug_status_timer.setInterval(1000)
        self._debug_status_timer.timeout.connect(self._refresh_debug_status)

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

    def _debug_configuration(self):
        if self.adb_remote.isChecked():
            host, port = remote_debug_endpoint(self.remote_host.text(), self.remote_port.value())
            return f"remote:{host}:{port}", f"Quelle: Remote\nEndpunkt: {host}:{port}", lambda: TcpDebugSource(host, port)
        port = resolve_phnix_debug_port()
        if not port:
            return "local:MI_04", "Quelle: Lokal\nEndpunkt: MI_04", lambda: (_ for _ in ()).throw(OSError("COM-Port MI_04 nicht verfügbar"))
        return f"local:{port}", f"Quelle: Lokal\nEndpunkt: {port} / MI_04", lambda: QtSerialDebugSource(port)

    def _update_debug_configuration(self):
        """Resolve MI_04 anew on every open after USB re-enumeration."""
        if self.adb_remote.isChecked():
            return (*self._debug_configuration(), None)

        def open_current_mi04():
            port = resolve_phnix_debug_port()
            if not port:
                raise OSError("COM-Port MI_04 nicht verfügbar")
            return QtSerialDebugSource(port)

        return (
            "local:MI_04", "Quelle: Lokal\nEndpunkt: MI_04 (automatischer Reconnect)",
            open_current_mi04, 1.5,
        )

    def _new_debug_capture(self) -> PhnixDebugCapture:
        identity, _description, factory = self._debug_configuration()
        return PhnixDebugCapture(factory, identity)

    def _ensure_debug_capture(self, *, for_update=False) -> PhnixDebugCapture:
        reconnect_interval = None
        if for_update:
            identity, description, factory, reconnect_interval = self._update_debug_configuration()
        else:
            identity, description, factory = self._debug_configuration()
        old = self._debug_capture
        if old is None or (old.identity != identity and not old.has_consumer("update")):
            window_was_connected = bool(old and old.has_consumer("window"))
            if old:
                old.remove_consumer("window")
                old.remove_status_consumer("ui")
                old.remove_status_consumer("log")
            self._debug_capture = PhnixDebugCapture(
                factory, identity, reconnect_interval=reconnect_interval
            )
            self._debug_source_description = description
            self._debug_last_data = None
            self._debug_connected_since = None
            if window_was_connected and for_update:
                self._attach_monitor_consumer(self._debug_capture)
        return self._debug_capture

    def _attach_monitor_consumer(self, capture):
        capture.add_status_consumer("ui", lambda status, error: self._debug_signals.status.emit(status, error))
        return capture.add_consumer("window", lambda line, event: self._debug_signals.line.emit(line, event))

    def _connect_debug_monitor(self):
        capture = self._ensure_debug_capture()
        if not capture.active:
            self._debug_last_data = None
            self._debug_connected_since = None
        self._attach_monitor_consumer(capture)

    def _disconnect_debug_monitor(self):
        if self._debug_capture:
            self._debug_capture.remove_consumer("window")
            self._debug_capture.remove_status_consumer("ui")
        if self._debug_window:
            if self._debug_capture and self._debug_capture.has_consumer("update"):
                self._debug_window.status.setText(
                    "Monitor getrennt – LTE-Logging für laufendes Update weiterhin verbunden."
                )
            else:
                self._debug_window.status.setText("Status: Getrennt")

    def _open_debug_monitor(self):
        if self._debug_window is None:
            self._debug_window = PhnixDebugWindow()
            self._debug_window.closed.connect(self._close_debug_monitor)
            self._debug_window.connect_requested.connect(self._connect_debug_monitor)
            self._debug_window.disconnect_requested.connect(self._disconnect_debug_monitor)
            self._connect_debug_monitor()
        self._debug_window.show()
        self._debug_window.raise_()
        self._debug_window.activateWindow()

    def _close_debug_monitor(self):
        self._disconnect_debug_monitor()
        self._debug_window = None

    def closeEvent(self, event):
        if self._debug_window is not None:
            self._debug_window.close()
        super().closeEvent(event)

    def _debug_line(self, line: str, event: object):
        self._debug_last_data = datetime.now()
        if self._debug_window:
            self._debug_window.append_line(line)
        if not self._debug_status_timer.isActive():
            self._debug_status_timer.start()

    def _refresh_debug_status(self):
        if self._debug_capture:
            self._debug_status(self._debug_capture.status, self._debug_capture.last_error)
        if not self._debug_window:
            self._debug_status_timer.stop()

    def _debug_status(self, status: str, error: object):
        now = datetime.now()
        if status == "Verbunden" and self._last_debug_status != "Verbunden":
            self._debug_connected_since = now
        self._last_debug_status = status
        if status in {"Getrennt", "Verbindung beendet", "Verbindung fehlgeschlagen"}:
            self._phnix_transfer_event = None
            self._render_transfer_progress()
        capture = self._debug_capture
        if (
            status == "Verbindung fehlgeschlagen"
            and capture
            and capture.has_consumer("update")
            and not self._debug_open_warning_shown
        ):
            self._debug_open_warning_shown = True
            warning = (
                "Remote PHNIX-Debugstream nicht erreichbar – Fortsetzung ohne LTE-Debug."
                if capture.identity.startswith("remote:") else
                "PHNIX LTE-Debugport nicht verfügbar – Update wird ohne LTE-Debuglog fortgesetzt."
            )
            self._log("[Warnung] " + warning)
        details = [f"Status: {status}", self._debug_source_description]
        if self._debug_connected_since and status == "Verbunden":
            details.append("Verbunden seit: " + self._debug_connected_since.strftime("%H:%M:%S"))
        if self._debug_last_data:
            details.append("Letzte Daten: " + self._debug_last_data.strftime("%H:%M:%S"))
        if error:
            details.append("Hinweis: " + str(error))
        if self._debug_window:
            self._debug_window.status.setText("\n".join(details))

    def _update_debug_line(self, line: str, event: object):
        if self._lte_log:
            try:
                stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                explained = explain_debug_line(line).splitlines()
                self._lte_log.write(f"[{stamp}] {explained[0]}\n")
                for explanation in explained[1:]:
                    self._lte_log.write(f"[{stamp}] {explanation}\n")
                self._lte_log.flush()
            except OSError as error:
                self._lte_log = None
                self._log(f"[Warnung] Automatisches LTE-Log konnte nicht weitergeschrieben werden: {error}")
        # Supplementary progress is shown only once the controller has authoritatively entered C5A8.
        if getattr(event, "kind", None) == "transfer-progress" and "phase-c5a8" in self._flow_steps:
            self._phnix_transfer_event = event
            self._render_transfer_progress()
        self._apply_debug_event(event)
        for completion_event in completion_events_for_line(line):
            self._observe_serial_completion(completion_event, self._update_run_generation)

    def _serial_fallback_allowed(self, generation: int) -> bool:
        return bool(
            generation == self._update_run_generation
            and self._serial_c5a8_started
            and self._serial_transfer_started
            and self._serial_capture_identity is not None
            and self._debug_capture
            and self._debug_capture.identity == self._serial_capture_identity
        )

    def _observe_serial_completion(self, event: object, generation: int) -> None:
        sequence = self._serial_sequence
        if (
            sequence is None or not self._serial_fallback_allowed(generation)
        ):
            return
        complete = sequence.observe(event, generation)
        if self._serial_monitoring_lost and not complete:
            kind = getattr(event, "kind", None)
            if kind == "manufacturer-success":
                self.progress_text.setText(
                    "PHNIX-Originaldienst meldet erfolgreichen Mainboard-Abschluss – "
                    "vollständige Abschlusssequenz wird noch geprüft."
                )
            elif kind in {"transfer-complete", "cloud-progress", "manufacturer-finished"}:
                self.progress_text.setText(
                    "PHNIX-Originaldienst meldet Mainboard-Fortschritt – "
                    "Controllerstatus derzeit nicht bestätigt."
                )
        if self._serial_monitoring_lost and complete and not self._serial_fallback_success:
            self._confirm_serial_completion(generation)

    def _confirm_serial_completion(self, generation: int) -> None:
        if not self._serial_fallback_allowed(generation):
            return
        try:
            desktop.windows_wrapper.clear_cache_pending()
        except OSError as error:
            self._log(f"[Warnung] Lokaler Update-Schutz konnte nicht abgeschlossen werden: {error}")
        self._serial_fallback_success = True
        self._serial_success_tail_generation = generation
        self._serial_reattach_pending_generation = generation
        self._flow_title = "Firmwareupdate erfolgreich"
        self._set_step(
            "update-result", "ok",
            "Firmwareupdate erfolgreich abgeschlossen. Abschluss wurde über den PHNIX-Originaldienst bestätigt.",
        )
        self._set_step(
            "phase-c5a8", "ok",
            "PHNIX-Originaldienst bestätigt die vollständige Mainboard-Abschlusssequenz.",
        )
        self.progress.setValue(100)
        self.progress_text.setText(
            "Firmwareupdate erfolgreich über PHNIX bestätigt. "
            "ADB-Verbindung wird zur Abschlusskontrolle erneut hergestellt …"
        )
        self.ota_reattach_btn.setVisible(True)
        if hasattr(self, "_stop_ota_elapsed"):
            self._stop_ota_elapsed()
        self._render_flow()
        QTimer.singleShot(3000, lambda: self._finish_automatic_logs(generation))
        QTimer.singleShot(100, lambda: self._serial_reattach(generation))

    def _serial_reattach(self, generation: int) -> None:
        if (
            generation != self._update_run_generation
            or not self._serial_fallback_success
            or self._serial_reattach_pending_generation != generation
            or self._serial_reattach_started_generation == generation
            or self.busy
        ):
            return
        self._serial_reattach_pending_generation = None
        self._serial_reattach_started_generation = generation
        self._reattach_ota()

    def _automatic_monitoring_reattach(self):
        if self._serial_fallback_success:
            self._serial_reattach(self._update_run_generation)
            return
        super()._automatic_monitoring_reattach()

    def _render_transfer_progress(self):
        """Render diagnostics separately; the controller phase headline stays stable."""
        if "phase-c5a8" not in self._flow_steps:
            return
        lines = []
        event = self._phnix_transfer_event
        controller = self._controller_transfer
        if event is not None:
            percent = event.progress
            self.progress.setValue(round(percent))
            self.progress_percent_label.setText(f"{percent:.1f} %")
            lines.append(
                (f"PHNIX Originaldienst: {percent:.1f} % · {event.current:,} / "
                 f"{event.total:,} Byte").replace(",", ".")
            )
        elif controller is not None:
            offset, length, percent = controller
            self.progress.setValue(percent)
            self.progress_percent_label.setText(f"{percent} %")
        if controller is not None:
            offset, length, percent = controller
            lines.append(
                (f"Windows Updater: {percent} % · {offset:,} / {length:,} Byte").replace(",", ".")
            )
        self.progress_sources.setText("\n".join(lines))

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
            text = (
                "PHNIX-Originaldienst meldet erfolgreichen Mainboard-Abschluss – "
                "vollständige Abschlusssequenz wird noch geprüft."
                if self._serial_monitoring_lost else
                "PHNIX-Originaldienst meldet Mainboard-Update erfolgreich – abschließende Controllerprüfung läuft."
            )
            self._update_existing_debug_step("phase-c5a8", "warn", text)
        elif kind == "mqtt-normal":
            self._update_existing_debug_step(
                "preflight-mqtt", "ok",
                "PHNIX-Originaldienst meldet Aliyun/MQTT als verbunden.",
            )
        # CMD_OTA progress and manufacturer messages remain log-only diagnostics;
        # controller phases and terminal decisions are never synthesized here.

    def _handle_record(self, record: dict):
        super()._handle_record(record)
        phase = self._record_phase(record)
        if phase == "c5a8":
            self._serial_c5a8_started = True
        if record.get("transfer_started") is True:
            self._serial_transfer_started = True
        if record.get("event") in {
            "monitoring-connection-lost", "monitoring-recovered-passive",
            "monitoring-detached-passive",
        }:
            self._serial_monitoring_lost = True
            if (
                self._serial_sequence
                and self._serial_sequence.complete
                and not self._serial_fallback_success
            ):
                self._confirm_serial_completion(self._update_run_generation)

    def _start_automatic_logs(self, manifest: Path) -> None:
        self._finish_automatic_logs()
        self._update_run_generation += 1
        generation = self._update_run_generation
        self._serial_sequence = SerialCompletionSequence(generation)
        self._serial_c5a8_started = False
        self._serial_transfer_started = False
        self._serial_monitoring_lost = False
        self._serial_fallback_success = False
        self._serial_capture_identity = None
        self._serial_success_tail_generation = None
        self._serial_reattach_pending_generation = None
        self._serial_reattach_started_generation = None
        self._phnix_transfer_event = None
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        firmware_directory = manifest.parent
        directory = firmware_directory / "Logs"
        try:
            directory.mkdir(exist_ok=True)
            self._automatic_log = (directory / f"FoxAir_Update_{stamp}.log").open("a", encoding="utf-8")
            self._lte_log = (directory / f"FoxAir_Update_{stamp}_LTE.log").open("a", encoding="utf-8")
        except OSError as error:
            for stream in (self._automatic_log, self._lte_log):
                if stream:
                    stream.close()
            self._automatic_log = self._lte_log = None
            self._log(
                "[Warnung] Ordner „Logs“ konnte nicht verwendet werden. "
                "Update-Logs werden direkt im Firmware-Verzeichnis gespeichert. "
                f"({error})"
            )
            try:
                self._automatic_log = (
                    firmware_directory / f"FoxAir_Update_{stamp}.log"
                ).open("a", encoding="utf-8")
                self._lte_log = (
                    firmware_directory / f"FoxAir_Update_{stamp}_LTE.log"
                ).open("a", encoding="utf-8")
            except OSError as fallback_error:
                for stream in (self._automatic_log, self._lte_log):
                    if stream:
                        stream.close()
                self._automatic_log = self._lte_log = None
                self._log(
                    "[Warnung] Automatische Update-Logs konnten nicht angelegt werden: "
                    f"{fallback_error}"
                )
        capture = self._ensure_debug_capture(for_update=True)
        self._debug_open_warning_shown = False
        self._serial_capture_identity = capture.identity
        if not capture.active:
            self._debug_last_data = None
            self._debug_connected_since = None
        capture.add_status_consumer("log", self._debug_log_status, notify_initial=False)
        capture.add_status_consumer(
            "progress", lambda status, error: self._debug_signals.status.emit(status, error)
        )
        capture.add_consumer(
            "update", lambda line, event, run=generation: self._debug_signals.update_line.emit(
                run, line, event
            )
        )

    def _update_debug_line_for_run(self, generation: int, line: str, event: object) -> None:
        if generation == self._update_run_generation:
            self._update_debug_line(line, event)

    def _finish_automatic_logs(self, generation: int | None = None) -> None:
        if generation is not None and generation != self._update_run_generation:
            return
        if self._debug_capture:
            self._debug_capture.remove_consumer("update")
            self._debug_capture.remove_status_consumer("log")
            self._debug_capture.remove_status_consumer("progress")
        for stream_name in ("_automatic_log", "_lte_log"):
            stream = getattr(self, stream_name, None)
            if stream:
                try:
                    stream.close()
                except OSError:
                    pass
            setattr(self, stream_name, None)

    def _debug_log_status(self, status: str, error: str | None) -> None:
        if not self._lte_log:
            return
        stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        labels = {
            "Verbinde …": "Verbinde",
            "Verbunden": "Verbunden",
            "Getrennt": "Verbindung getrennt",
            "Verbindung beendet": "Verbindung beendet",
            "Verbindung fehlgeschlagen": "Verbindung fehlgeschlagen",
        }
        endpoint = self._debug_capture.identity if self._debug_capture else ""
        detail = (" " + endpoint if status == "Verbinde …" and endpoint else "")
        if error:
            detail += f": {error}"
        try:
            self._lte_log.write(f"[{stamp}] [DEBUG] {labels.get(status, status)}{detail}\n")
            self._lte_log.flush()
        except OSError:
            pass

    def _run(self, op, command, cwd=None):
        if op in {"dry", "update"}:
            try:
                index = command.index("--manifest")
                manifest = Path(command[index + 1])
            except (ValueError, IndexError):
                manifest = None
            if manifest and manifest.is_file():
                self._start_automatic_logs(manifest)
        if op == "update" and getattr(self, "restart_before_update", None) is not None:
            if self.restart_before_update.isChecked():
                adb_path = self._require_adb()
                if not adb_path:
                    self._finish_automatic_logs()
                    return
                self.busy = True
                self._buttons()
                self._pending_update_start = (op, list(command), cwd)
                client = AdbClient(adb_path, env=self._process_env())

                def work():
                    try:
                        message = restart_phnix_iot_service(client)
                        pid = wait_for_phnix_runtime_ready(client)
                    except Exception as error:
                        self._pre_update_restart_signals.done.emit(False, str(error))
                    else:
                        self._pre_update_restart_signals.done.emit(
                            True, f"{message}\nDienst und MQTT bereit (PID {pid})."
                        )

                threading.Thread(
                    target=work, daemon=True, name="phnix-pre-update-restart"
                ).start()
                return
        super()._run(op, command, cwd)

    def _pre_update_restart_finished(self, success: bool, message: str) -> None:
        pending = self._pending_update_start
        self._pending_update_start = None
        self.busy = False
        self._buttons()
        if not success or pending is None:
            self._log(f"[Fehler] Kontrollierter phnixIot4G-Neustart fehlgeschlagen: {message}")
            self._finish_automatic_logs()
            QMessageBox.critical(
                self, "Firmwareupdate nicht gestartet",
                "Der kontrollierte Neustart oder die anschließende LTE-/MQTT-Bereitschaft "
                "konnte nicht bestätigt werden. Das Firmwareupdate wurde nicht gestartet.\n\n"
                + message,
            )
            return
        self._log(message)
        op, command, cwd = pending
        super()._run(op, command, cwd)

    def _done(self, op, code, output):
        generation = self._update_run_generation
        keep_success_tail = (
            op == "update"
            and self._serial_fallback_success
            and self._serial_success_tail_generation == generation
        )
        keep_serial_tail = (
            op == "update"
            and self._serial_monitoring_lost
            and self._serial_c5a8_started
            and self._serial_transfer_started
            and not self._serial_fallback_success
        )
        if op in {"dry", "update"}:
            if keep_success_tail or keep_serial_tail:
                if self._automatic_log:
                    try:
                        self._automatic_log.close()
                    except OSError:
                        pass
                    self._automatic_log = None
                if keep_serial_tail:
                    QTimer.singleShot(600000, lambda: self._finish_automatic_logs(generation))
            else:
                # Must happen before the base implementation can open a modal QMessageBox.
                self._finish_automatic_logs()
        if op == "update" and self._serial_fallback_success:
            # Preserve the already terminal PHNIX result while still running the
            # generic process/button cleanup.  The normal update handler would
            # reinterpret the controller's non-zero monitoring-loss exit.
            super()._done("handled-result", code, output)
            self._serial_reattach(generation)
            return
        if op == "update" and self._has_event(
            self._records(output), "monitoring-detached-passive"
        ):
            super()._done("handled-result", code, output)
            self._flow_title = "Passive Firmwareüberwachung"
            self._set_step(
                "update-result", "warn",
                "ADB-/Controllerüberwachung beendet; PHNIX-Originaldienst und serieller Debugkanal laufen weiter.",
            )
            self.progress_text.setText(
                "ADB-/Controllerüberwachung wurde beendet. Der PHNIX-Originaldienst führt das "
                "Firmwareupdate selbstständig weiter. Der serielle PHNIX-Debugkanal wird weiterhin überwacht."
            )
            self._render_flow()
            return
        super()._done(op, code, output)
        if op == "ota-reattach" and self._serial_fallback_success:
            status = None
            json_start = output.find("{")
            if json_start >= 0:
                try:
                    candidate = json.loads(output[json_start:])
                    status = candidate if isinstance(candidate, dict) else None
                except json.JSONDecodeError:
                    pass
            hook = status.get("hook") if isinstance(status, dict) and isinstance(status.get("hook"), dict) else {}
            terminal_success = (
                code == 0
                and hook.get("phase") == "success"
                and hook.get("terminal") is True
            )
            if terminal_success:
                self.progress_text.setText(
                    "Firmwareupdate erfolgreich über PHNIX bestätigt. ADB-Abschlusskontrolle abgeschlossen."
                )
                self.ota_reattach_btn.setVisible(False)
            elif code == 0 and status is not None:
                self.progress_text.setText(
                    "Firmwareupdate erfolgreich über PHNIX bestätigt. "
                    "ADB-Verbindung wiederhergestellt – Abschlusskontrolle noch nicht terminal bestätigt."
                )
                self.ota_reattach_btn.setVisible(True)
            else:
                self.progress_text.setText(
                    "Firmwareupdate wurde vom PHNIX-Originaldienst erfolgreich bestätigt. "
                    "Die ADB-Verbindung zum LTE-Modem ist weiterhin unterbrochen; das "
                    "Mainboardupdate ist abgeschlossen. Das LTE-Modem kann jetzt erneut "
                    "verbunden werden. Remote-Aufräumarbeiten werden beim nächsten "
                    "erfolgreichen Verbindungsaufbau nachgeholt. "
                    "ADB-Abschlusskontrolle derzeit nicht möglich."
                )
                self.ota_reattach_btn.setVisible(True)

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
