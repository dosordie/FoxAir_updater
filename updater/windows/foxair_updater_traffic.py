"""Optional Modem Diagnose / Traffic tab, kept out of the updater core."""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QGroupBox, QHeaderView, QHBoxLayout, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

import foxair_updater_operator_display as operator
from updater.common.adb_transport import AdbClient
from updater.common.phnix_traffic import EventRing, TrafficTracer
from updater.common.phnix_traffic import DEFAULT_HOOKS, HOOKS


class TrafficSignals(QObject):
    result = Signal(str, str, str)
    error = Signal(str, str)


class MainWindow(operator.MainWindow):
    def __init__(self):
        self._traffic_ring = EventRing(500)
        self._traffic_running = False
        self._traffic_tracer = None
        self._traffic_signals = TrafficSignals()
        self._traffic_signals.result.connect(self._traffic_result)
        self._traffic_signals.error.connect(self._traffic_error)
        self._traffic_timer = QTimer()
        self._traffic_timer.setInterval(2000)
        self._traffic_timer.timeout.connect(self._traffic_poll)
        super().__init__()

    def _ui(self):
        super()._ui()
        self.traffic_tab_index = self.tabs.insertTab(
            self.modem_tab_index + 1, self._traffic_page(), "Modem Diagnose / Traffic"
        )
        self.tabs.setTabVisible(self.traffic_tab_index, self.show_modem_diagnostics.isChecked())

    def _traffic_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        note = QLabel("<b>Read-only Runtime-Trace.</b> Keine eigenen MQTT-/HTTP-Verbindungen, "
                      "kein RS485-Zugriff und keine Änderung an <code>/data/phnixIot4G</code>. "
                      "Der flüchtige GDB-Hook wird nur für die exakt geprüfte Build-ID aktiviert. "
                      "<b>Achtung:</b> Der Originaldienst kann nach einem Trace zeitverzögert durch "
                      "seine Überwachung neu gestartet werden.")
        note.setWordWrap(True); layout.addWidget(note)
        hooks_box = QGroupBox("Zu verwendende Hooks"); hooks_layout = QGridLayout(hooks_box)
        hooks_layout.setContentsMargins(6, 4, 6, 4); hooks_layout.setHorizontalSpacing(6)
        self.traffic_hooks = {}
        for column, group in enumerate(("MQTT", "HTTP / OTA", "Provisionierung")):
            group_box = QGroupBox(group); group_layout = QVBoxLayout(group_box)
            group_layout.setContentsMargins(5, 3, 5, 3); group_layout.setSpacing(1)
            for hook_id, (hook_group, label) in HOOKS.items():
                if hook_group != group: continue
                checkbox = QCheckBox(label); checkbox.setChecked(hook_id in DEFAULT_HOOKS)
                checkbox.setStyleSheet("QCheckBox { font-size: 10px; }")
                self.traffic_hooks[hook_id] = checkbox; group_layout.addWidget(checkbox)
            hooks_layout.addWidget(group_box, 0, column)
        layout.addWidget(hooks_box)
        row = QHBoxLayout()
        self.traffic_enable = QCheckBox("Diagnose aktivieren")
        self.traffic_enable.toggled.connect(self._traffic_toggle); row.addWidget(self.traffic_enable)
        self.traffic_delete = QCheckBox("Daten beim Deaktivieren löschen"); self.traffic_delete.setChecked(True)
        row.addWidget(self.traffic_delete)
        self.traffic_refresh_btn = QPushButton("Jetzt aktualisieren"); self.traffic_refresh_btn.clicked.connect(lambda _checked=False: self._traffic_poll(manual=True)); row.addWidget(self.traffic_refresh_btn)
        self.traffic_status = QLabel("Inaktiv"); row.addWidget(self.traffic_status, 1); layout.addLayout(row)
        self.traffic_mqtt = self._summary(layout, "MQTT")
        self.traffic_http = self._summary(layout, "HTTP / OTA")
        self.traffic_provision = self._summary(layout, "Provisionierung")
        raw = QGroupBox("Rohereignisse (Ringbuffer: 500)"); raw_layout = QVBoxLayout(raw)
        self.traffic_table = QTableWidget(0, 6)
        self.traffic_table.setHorizontalHeaderLabels(["Zeit", "Richtung", "Protokoll", "Kanal", "Länge", "Inhalt"])
        header = self.traffic_table.horizontalHeader()
        for column in range(5):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        raw_layout.addWidget(self.traffic_table)
        layout.addWidget(raw, 1)
        return page

    @staticmethod
    def _summary(layout, title):
        box = QGroupBox(title); inner = QVBoxLayout(box); label = QLabel("Noch kein Ereignis.")
        label.setWordWrap(True); inner.addWidget(label); layout.addWidget(box); return label

    def _selected_traffic_hooks(self):
        return tuple(hook_id for hook_id, checkbox in self.traffic_hooks.items() if checkbox.isChecked())

    def _tracer(self):
        if self._traffic_tracer is not None:
            return self._traffic_tracer
        adb = self._require_adb()
        if not adb: return None
        helper = operator.lte.desktop.app.base.backend_dir() / "tools/phnix_traffic/foxair_traffic_trace"
        self._traffic_tracer = TrafficTracer(AdbClient(adb, env=self._process_env()), helper)
        return self._traffic_tracer

    def _traffic_toggle(self, checked):
        if self.busy:
            return
        hooks = self._selected_traffic_hooks()
        if checked and not hooks:
            self.traffic_enable.blockSignals(True); self.traffic_enable.setChecked(False); self.traffic_enable.blockSignals(False)
            self.traffic_status.setText("Kein Hook ausgewählt")
            self._log("[Modem Diagnose / Traffic] Start verweigert: Kein Hook ausgewählt.")
            return
        tracer = self._tracer()
        if tracer is None:
            self.traffic_enable.blockSignals(True); self.traffic_enable.setChecked(False); self.traffic_enable.blockSignals(False); return
        if checked:
            self._log("[Modem Diagnose / Traffic] Aktivierte Hooks:\n" +
                      "\n".join(f"- {hook}" for hook in hooks))
        self._traffic_work("enable" if checked else "disable", tracer, hooks=hooks)

    def _traffic_poll(self, manual=False):
        if not self.traffic_enable.isChecked() or self._traffic_running: return
        tracer = self._tracer()
        if tracer: self._traffic_work("refresh" if manual else "poll", tracer)

    def _traffic_work(self, action, tracer, *, hooks=()):
        if self._traffic_running: return
        self._traffic_running = True; self.traffic_status.setText("Bitte warten …")
        descriptions = {
            "enable": ("Diagnose wird aktiviert: SHA256 wird direkt auf dem Modem geprüft; "
                       "anschließend werden PID, Prozess-Lebendigkeit, /proc/<PID>/exe und "
                       "/proc/<PID>/maps unmittelbar vor dem gdbserver-Attach erneut geprüft."),
            "disable": "Diagnose wird deaktiviert; der temporäre Hook wird entfernt.",
            "refresh": "Traffic-Daten werden jetzt manuell aktualisiert.",
        }
        if action in descriptions:
            self._log("[Modem Diagnose / Traffic] " + descriptions[action])
        delete_data = self.traffic_delete.isChecked()
        def work():
            try:
                if action == "enable":
                    status = tracer.enable(hooks, mode="full")
                    data = tracer.events() if status.startswith("active") else tracer.startup_diagnostics
                elif action == "disable": tracer.disable(delete_data=delete_data); status = "inactive"; data = ""
                else: status = tracer.status(); data = tracer.events() if status.startswith("active") else ""
                self._traffic_signals.result.emit(action, status, data)
            except Exception as error: self._traffic_signals.error.emit(action, str(error))
        threading.Thread(target=work, daemon=True).start()

    def _traffic_result(self, action, status, data):
        self._traffic_running = False
        if status.startswith("critical|"):
            fields = dict(part.split("=", 1) for part in status.split("|")[2:] if "=" in part)
            reason = status.split("|", 2)[1]
            if reason == "sigsegv":
                message = "phnixIot4G erhielt SIGSEGV während aktiven Hooks: " + fields.get("hooks", "unbekannt")
            elif reason == "pid_changed":
                message = ("phnixIot4G wurde während des Traces neu gestartet. "
                           f"PID alt: {fields.get('old_pid', '?')}, PID neu: {fields.get('new_pid', '?')}")
            else:
                message = "Debugger wurde unerwartet beendet; aktive Hooks: " + fields.get("hooks", "unbekannt")
            self._log("[Modem Diagnose / Traffic] KRITISCH:\n" + message)
            self._log("[Modem Diagnose / Traffic] Aufgezeichnete Ereignisse bleiben zur Analyse erhalten.")
        if not status.startswith("active"):
            self._traffic_timer.stop(); self.traffic_status.setText("Inaktiv (Prozess/Hook beendet)")
            if self.traffic_enable.isChecked():
                self.traffic_enable.blockSignals(True); self.traffic_enable.setChecked(False); self.traffic_enable.blockSignals(False)
            delete_data = action == "disable" and self.traffic_delete.isChecked()
            if delete_data:
                self._traffic_ring.clear()
            self._traffic_tracer = None
            if action == "enable":
                self._log("[Modem Diagnose / Traffic] Start fehlgeschlagen; Debug-Dateien bleiben "
                          "auf dem Modem erhalten. Debugger-Ausgaben:\n" + (data or "<keine Ausgabe>"))
            elif action == "disable" and delete_data:
                self._log("[Modem Diagnose / Traffic] Diagnose deaktiviert; Trace-Daten wurden gelöscht.")
            elif action == "disable":
                self._log("[Modem Diagnose / Traffic] Diagnose deaktiviert; Trace-Daten bleiben erhalten.")
            elif not status.startswith("critical|"):
                self._log("[Modem Diagnose / Traffic] Diagnose wurde beendet; aufgezeichnete Ereignisse "
                          "bleiben zur Analyse erhalten.")
        else:
            self.traffic_status.setText("Aktiv – passiv angehängt"); self._traffic_timer.start()
            added = self._traffic_ring.add_json_lines(data)
            if action == "enable":
                self._log("[Modem Diagnose / Traffic] Diagnose ist aktiv und passiv angehängt; "
                          "alle modemseitigen Sicherheitsprüfungen wurden bestanden.")
            elif action == "refresh":
                self._log(f"[Modem Diagnose / Traffic] Aktualisierung abgeschlossen: {added} neue Ereignisse.")
            elif added:
                self._log(f"[Modem Diagnose / Traffic] {added} neue Ereignisse empfangen.")
        self._render_traffic()

    def _traffic_error(self, action, message):
        self._traffic_running = False; self._traffic_timer.stop(); self.traffic_status.setText("Fehler: " + message)
        self.traffic_enable.blockSignals(True); self.traffic_enable.setChecked(False); self.traffic_enable.blockSignals(False)
        self._log("[Modem Diagnose / Traffic] Fehler: " + message)
        if action in ("poll", "refresh", "disable"):
            self._log("[Modem Diagnose / Traffic] Verbindung zum Trace verloren; bereits aufgezeichnete "
                      "Ereignisse bleiben erhalten.")
        else:
            self._log("[Modem Diagnose / Traffic] Start fehlgeschlagen; bereits aufgezeichnete Ereignisse "
                      "bleiben erhalten.")

    def _render_traffic(self):
        events = self._traffic_ring.snapshot(); self.traffic_table.setRowCount(len(events))
        for row, event in enumerate(events):
            values = [event.timestamp[11:19], event.direction.upper(), event.protocol.upper(), event.channel,
                      f"{event.length} B", event.summary]
            for col, value in enumerate(values): self.traffic_table.setItem(row, col, QTableWidgetItem(value))
        mqtt = [e for e in events if e.protocol == "mqtt"]
        self.traffic_mqtt.setText("<br>".join(
            f"{e.direction.upper()} {e.channel}: {e.length} B – {e.summary}" for e in mqtt[-3:]
        ) or "Noch kein Ereignis.")
        starts = [e for e in events if e.channel == "ota_download_start"]
        if starts:
            start = starts[-1]; fields = start.fields
            start_index = max(i for i, event in enumerate(events) if event is start)
            chunks = [e for e in events[start_index + 1:] if e.channel == "ota_chunk"]
            self.traffic_http.setText(
                f"Typ: {fields.get('download_type', 'unbekannt')}<br>URL: {fields.get('url', '–')}<br>"
                f"Ziel: {fields.get('target', '–')}<br>Empfang: "
                + f"{sum(e.length for e in chunks):,} Byte".replace(",", ".")
                + f"<br>Status: {fields.get('status', 'aktiv')}<br>MD5: nicht sicher verfügbar"
            )
        else: self.traffic_http.setText("Noch kein Ereignis.")
        prov = [e for e in events if "register" in e.channel or "queryiotdevice" in e.channel]
        self.traffic_provision.setText(prov[-1].channel if prov else "Noch kein Ereignis.")

    def _buttons(self):
        super()._buttons()
        if hasattr(self, "traffic_enable"):
            enabled = not self.busy and not self._traffic_running
            self.traffic_enable.setEnabled(enabled)
            self.traffic_refresh_btn.setEnabled(enabled and self.traffic_enable.isChecked())
            for checkbox in self.traffic_hooks.values():
                checkbox.setEnabled(enabled and not self.traffic_enable.isChecked())
