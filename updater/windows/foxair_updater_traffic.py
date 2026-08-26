"""Optional Modem Diagnose / Traffic tab, kept out of the updater core."""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QGroupBox, QHBoxLayout, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

import foxair_updater_operator_display as operator
from updater.common.adb_transport import AdbClient
from updater.common.phnix_traffic import EventRing, TrafficTracer


class TrafficSignals(QObject):
    result = Signal(str, str)
    error = Signal(str)


class MainWindow(operator.MainWindow):
    def __init__(self):
        self._traffic_ring = EventRing(500)
        self._traffic_running = False
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

    def _traffic_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        note = QLabel("<b>Optionaler passiver Runtime-Trace.</b> Keine eigenen MQTT-/HTTP-Verbindungen, "
                      "kein RS485-Zugriff und keine Änderung an <code>/data/phnixIot4G</code>. "
                      "Der flüchtige GDB-Hook wird nur für die exakt geprüfte Build-ID aktiviert.")
        note.setWordWrap(True); layout.addWidget(note)
        row = QHBoxLayout()
        self.traffic_enable = QCheckBox("Diagnose aktivieren")
        self.traffic_enable.toggled.connect(self._traffic_toggle); row.addWidget(self.traffic_enable)
        self.traffic_delete = QCheckBox("Daten beim Deaktivieren löschen"); self.traffic_delete.setChecked(True)
        row.addWidget(self.traffic_delete)
        refresh = QPushButton("Jetzt aktualisieren"); refresh.clicked.connect(self._traffic_poll); row.addWidget(refresh)
        self.traffic_status = QLabel("Inaktiv"); row.addWidget(self.traffic_status, 1); layout.addLayout(row)
        self.traffic_mqtt = self._summary(layout, "MQTT")
        self.traffic_http = self._summary(layout, "HTTP / OTA")
        self.traffic_provision = self._summary(layout, "Provisionierung")
        raw = QGroupBox("Rohereignisse (Ringbuffer: 500)"); raw_layout = QVBoxLayout(raw)
        self.traffic_table = QTableWidget(0, 6)
        self.traffic_table.setHorizontalHeaderLabels(["Zeit", "Richtung", "Protokoll", "Kanal", "Länge", "Kurzinhalt"])
        self.traffic_table.horizontalHeader().setStretchLastSection(True); raw_layout.addWidget(self.traffic_table)
        layout.addWidget(raw, 1)
        return page

    @staticmethod
    def _summary(layout, title):
        box = QGroupBox(title); inner = QVBoxLayout(box); label = QLabel("Noch kein Ereignis.")
        label.setWordWrap(True); inner.addWidget(label); layout.addWidget(box); return label

    def _tracer(self):
        adb = self._require_adb()
        if not adb: return None
        helper = operator.lte.desktop.app.base.backend_dir() / "tools/phnix_traffic/foxair_traffic_trace"
        return TrafficTracer(AdbClient(adb, env=self._process_env()), helper)

    def _traffic_toggle(self, checked):
        tracer = self._tracer()
        if tracer is None:
            self.traffic_enable.blockSignals(True); self.traffic_enable.setChecked(False); self.traffic_enable.blockSignals(False); return
        self._traffic_work("enable" if checked else "disable", tracer)

    def _traffic_poll(self):
        if not self.traffic_enable.isChecked() or self._traffic_running: return
        tracer = self._tracer()
        if tracer: self._traffic_work("poll", tracer)

    def _traffic_work(self, action, tracer):
        if self._traffic_running: return
        self._traffic_running = True; self.traffic_status.setText("Bitte warten …")
        def work():
            try:
                if action == "enable": status = tracer.enable(); data = tracer.events()
                elif action == "disable": tracer.disable(delete_data=self.traffic_delete.isChecked()); status = "inactive"; data = ""
                else: status = tracer.status(); data = tracer.events() if status == "active" else ""
                self._traffic_signals.result.emit(status, data)
            except Exception as error: self._traffic_signals.error.emit(str(error))
        threading.Thread(target=work, daemon=True).start()

    def _traffic_result(self, status, data):
        self._traffic_running = False
        if status != "active":
            self._traffic_timer.stop(); self.traffic_status.setText("Inaktiv (Prozess/Hook beendet)")
            if self.traffic_enable.isChecked():
                self.traffic_enable.blockSignals(True); self.traffic_enable.setChecked(False); self.traffic_enable.blockSignals(False)
            if self.traffic_delete.isChecked(): self._traffic_ring.clear()
        else:
            self.traffic_status.setText("Aktiv – passiv angehängt"); self._traffic_timer.start()
            self._traffic_ring.clear(); self._traffic_ring.add_json_lines(data)
        self._render_traffic()

    def _traffic_error(self, message):
        self._traffic_running = False; self._traffic_timer.stop(); self.traffic_status.setText("Fehler: " + message)
        self.traffic_enable.blockSignals(True); self.traffic_enable.setChecked(False); self.traffic_enable.blockSignals(False)

    def _render_traffic(self):
        events = self._traffic_ring.snapshot(); self.traffic_table.setRowCount(len(events))
        latest = {}
        for row, event in enumerate(events):
            latest[(event.protocol, event.channel)] = event
            short = event.payload_hex or event.payload_text or ("chunk" if event.payload_type == "chunk" else "")
            values = [event.timestamp[11:19], event.direction.upper(), event.protocol.upper(), event.channel,
                      f"{event.length} B", short[:80]]
            for col, value in enumerate(values): self.traffic_table.setItem(row, col, QTableWidgetItem(value))
        mqtt = [e for e in events if e.protocol == "mqtt"]
        self.traffic_mqtt.setText("<br>".join(f"{e.direction.upper()} {e.channel}: {e.length} B – {(e.payload_hex or '')[:48]}" for e in mqtt[-3:]) or "Noch kein Ereignis.")
        chunks = [e for e in events if e.protocol in ("http", "https")]
        self.traffic_http.setText(f"Empfangene OTA-Daten: {sum(e.length for e in chunks):,} Byte".replace(",", ".") if chunks else "Noch kein Ereignis.")
        prov = [e for e in events if "register" in e.channel or "queryiotdevice" in e.channel]
        self.traffic_provision.setText(prov[-1].channel if prov else "Noch kein Ereignis.")
