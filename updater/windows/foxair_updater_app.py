from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from html import escape
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
)

import foxair_updater_gui as base
import release_check


APP_VERSION = "0.2.96"
MODEM_DRIVER_URL = "https://files.waveshare.com/upload/2/24/SIMCOM_Windows_USB_Drivers_V1.0.2.zip"
REMOTE_CACHE_FIRMWARE = "/cache/phnixIot_device_OTA"
REMOTE_CACHE_STAGE = "/cache/.phnixIot_device_OTA.manual-upload"

GREEN = "#16803a"
YELLOW = "#b26a00"
RED = "#b42318"
GRAY = "#667085"


class UpdateSignals(QObject):
    result = Signal(dict)
    error = Signal(str)


class MainWindow(base.MainWindow):
    """Windows UI enhancements layered around the unchanged OTA backend."""

    def __init__(self):
        self._flow_steps: dict[str, tuple[str, str]] = {}
        self._flow_title = "Noch kein Ablauf gestartet."
        self._release_check_running = False
        self._latest_release_url = release_check.UPDATE_RELEASES_URL
        self._update_signals = UpdateSignals()
        self._update_signals.result.connect(self._release_check_result)
        self._update_signals.error.connect(self._release_check_error)
        super().__init__()
        self.setWindowTitle(f"FoxAir Updater {APP_VERSION} – EXPERIMENTELL")

        # QSettings already stores ADB mode/path, Pi address/port and the backup
        # target in the base GUI. Persist manual edits as well and remember the
        # last directories used by firmware/manifest dialogs.
        self.backup_path.editingFinished.connect(self._persist_settings)
        self.update_manifest.editingFinished.connect(self._persist_settings)
        self.same_manifest.editingFinished.connect(self._persist_settings)
        self.firmware.editingFinished.connect(self._persist_settings)
        if hasattr(self, "cache_firmware"):
            self.cache_firmware.editingFinished.connect(self._persist_settings)
        QTimer.singleShot(900, lambda: self._check_for_updates(silent=True))

    def _load(self):
        """Load all connection values before signals are allowed to write them back."""
        saved_adb = str(self.settings.value("adb", "") or "")
        backup_value = str(
            self.settings.value("backup", Path.home() / "FoxAir_LTE_Backup")
        )
        remote = str(self.settings.value("adb_mode", "local")) == "remote"
        remote_host_value = str(self.settings.value("remote_host", "") or "")
        try:
            remote_port_value = int(self.settings.value("remote_port", 5038))
        except (TypeError, ValueError):
            remote_port_value = 5038

        found = (
            Path(saved_adb)
            if saved_adb and Path(saved_adb).is_file()
            else self._find_adb()
        )
        if found:
            self.adb.setText(str(found))
        self.backup_path.setText(backup_value)

        # The base GUI connects radio/text/value signals before _load(). Without
        # blocking them, setChecked() writes the still-empty host and default
        # port back to QSettings before they are read. That is why the previous
        # Windows build forgot the Raspberry-Pi IP (and could reset the port).
        widgets = (
            self.adb_remote,
            self.adb_local,
            self.remote_host,
            self.remote_port,
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.remote_host.setText(remote_host_value)
            self.remote_port.setValue(remote_port_value)
            self.adb_remote.setChecked(remote)
            self.adb_local.setChecked(not remote)
        finally:
            for widget in widgets:
                widget.blockSignals(False)

        self._remote_changed()
        self.settings.sync()

    def _connection(self):
        widget = super()._connection()
        layout = widget.layout()

        driver_row = QHBoxLayout()
        driver = QPushButton("SIMCom USB-Treiber herunterladen")
        driver.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(MODEM_DRIVER_URL)))
        driver_row.addWidget(driver)
        driver_note = QLabel("Für die direkte USB-Verbindung unter Windows zuerst den Modem-Treiber installieren.")
        driver_note.setWordWrap(True)
        driver_row.addWidget(driver_note, 1)
        # The existing Platform-Tools download row is item 1 in the base GUI.
        # Insert the modem driver directly before it, as prerequisite step 1.
        layout.insertLayout(1, driver_row)

        update_heading = QLabel("<b>Programmupdate</b>")
        self.release_status = QLabel(f"Installiert: v{APP_VERSION} – GitHub-Prüfung noch nicht ausgeführt.")
        self.release_status.setWordWrap(True)
        update_row = QHBoxLayout()
        self.release_check_btn = QPushButton("Auf neue Version prüfen")
        self.release_check_btn.clicked.connect(lambda: self._check_for_updates(silent=False))
        self.release_open_btn = QPushButton("GitHub Release öffnen")
        self.release_open_btn.setEnabled(False)
        self.release_open_btn.clicked.connect(self._open_latest_release)
        update_row.addWidget(self.release_check_btn)
        update_row.addWidget(self.release_open_btn)
        update_row.addStretch()

        # Keep the existing explanatory note and final stretch at the bottom.
        insert_at = max(0, layout.count() - 1)
        layout.insertWidget(insert_at, update_heading)
        layout.insertWidget(insert_at + 1, self.release_status)
        layout.insertLayout(insert_at + 2, update_row)
        return widget

    def _backup(self):
        widget = super()._backup()
        # A complete diagnostic backup should include the verified original LTE
        # service by default. Users can still deselect it explicitly.
        self.backup_service.setChecked(True)
        return widget

    def _advanced(self):
        widget = super()._advanced()
        layout = widget.layout()
        insert_at = max(0, layout.count() - 1)

        heading = QLabel("<b>Firmware manuell in den LTE-Cache kopieren</b>")
        layout.insertWidget(insert_at, heading)
        insert_at += 1

        row = QHBoxLayout()
        self.cache_firmware = QLineEdit()
        self.cache_firmware.setPlaceholderText("Firmwaredatei auswählen")
        self.cache_firmware.textChanged.connect(self._buttons)
        choose = QPushButton("Firmware…")
        choose.clicked.connect(self._pick_cache_firmware)
        row.addWidget(self.cache_firmware, 1)
        row.addWidget(choose)
        layout.insertLayout(insert_at, row)
        insert_at += 1

        note = QLabel(
            "Kopiert die gewählte Datei ausschließlich nach "
            "<code>/cache/phnixIot_device_OTA</code> auf dem LTE-Modem. "
            "Es wird kein OTA gestartet und nichts an das Mainboard gesendet. "
            "Die Datei wird zuerst unter einem temporären Namen übertragen, per SHA-256 "
            "geprüft und erst danach atomar auf den Originalpfad verschoben."
        )
        note.setWordWrap(True)
        layout.insertWidget(insert_at, note)
        insert_at += 1

        self.cache_copy_btn = QPushButton("Firmware nach /cache/phnixIot_device_OTA kopieren")
        self.cache_copy_btn.clicked.connect(self._manual_cache_copy)
        layout.insertWidget(insert_at, self.cache_copy_btn)
        return widget

    def _update(self):
        widget = super()._update()
        layout = widget.layout()

        heading = QLabel("<b>Ablauf / Sicherheitsstatus</b>")
        layout.insertWidget(2, heading)

        self.flow_status = QLabel()
        self.flow_status.setWordWrap(True)
        self.flow_status.setStyleSheet(
            "QLabel{background:#f7f8fa;border:1px solid #d0d5dd;padding:9px;}"
        )
        flow_font = self.flow_status.font()
        if flow_font.pointSize() > 0:
            flow_font.setPointSize(flow_font.pointSize() + 1)
        elif flow_font.pixelSize() > 0:
            flow_font.setPixelSize(flow_font.pixelSize() + 1)
        self.flow_status.setFont(flow_font)
        layout.insertWidget(3, self.flow_status)

        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Noch keine Firmwareübertragung")
        self._render_flow()
        return widget

    def _settings_directory(self, key: str, fallback: Path | None = None) -> Path:
        value = str(self.settings.value(key, "") or "").strip()
        if value:
            path = Path(value)
            if path.is_dir():
                return path
        return fallback or Path.home()

    def _remember_parent(self, key: str, value: str) -> None:
        text = str(value or "").strip().strip('"')
        if not text:
            return
        path = Path(text)
        parent = path if path.is_dir() else path.parent
        if parent and parent.exists():
            self.settings.setValue(key, str(parent))

    def _persist_settings(self) -> None:
        self.settings.setValue("adb", self.adb.text().strip().strip('"'))
        self.settings.setValue("backup", self.backup_path.text().strip())
        self.settings.setValue("adb_mode", "remote" if self.adb_remote.isChecked() else "local")
        self.settings.setValue("remote_host", self.remote_host.text().strip())
        self.settings.setValue("remote_port", self.remote_port.value())
        self._remember_parent("manifest_dir", self.update_manifest.text())
        self._remember_parent("manifest_dir", self.same_manifest.text())
        self._remember_parent("firmware_dir", self.firmware.text())
        if hasattr(self, "cache_firmware"):
            self._remember_parent("firmware_dir", self.cache_firmware.text())
        self.settings.sync()

    def _browse_adb(self):
        current = self.adb.text().strip().strip('"')
        current_path = Path(current) if current else None
        start = (
            current_path.parent
            if current_path and current_path.parent.is_dir()
            else self._settings_directory("adb_dir")
        )
        file_name, _ = QFileDialog.getOpenFileName(
            self, "adb.exe auswählen", str(start), "ADB (adb.exe)"
        )
        if file_name:
            self.adb.setText(file_name)
            self.settings.setValue("adb_dir", str(Path(file_name).parent))
            self._adb_changed()
            self.settings.sync()

    def _browse_backup(self):
        start = self.backup_path.text().strip() or str(self._settings_directory("backup"))
        directory = QFileDialog.getExistingDirectory(self, "Backup-Ziel", start)
        if directory:
            self.backup_path.setText(directory)
            self.settings.setValue("backup", directory)
            self.settings.sync()

    def _pick_manifest(self, field):
        current = field.text().strip()
        current_path = Path(current) if current else None
        start = (
            current_path.parent
            if current_path and current_path.parent.is_dir()
            else self._settings_directory("manifest_dir")
        )
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Manifest auswählen", str(start), "Manifest (*.json)"
        )
        if file_name:
            field.setText(file_name)
            self.settings.setValue("manifest_dir", str(Path(file_name).parent))
            self.settings.sync()

    def _pick_firmware(self):
        current = self.firmware.text().strip()
        current_path = Path(current) if current else None
        start = (
            current_path.parent
            if current_path and current_path.parent.is_dir()
            else self._settings_directory("firmware_dir")
        )
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Firmware auswählen",
            str(start),
            "Alle Dateien (*);;BIN-Dateien (*.bin)",
        )
        if file_name:
            self.firmware.setText(file_name)
            self.settings.setValue("firmware_dir", str(Path(file_name).parent))
            self.settings.sync()
            self.manifest_preview.clear()
            self._buttons()

    def _pick_cache_firmware(self):
        current = self.cache_firmware.text().strip()
        current_path = Path(current) if current else None
        start = (
            current_path.parent
            if current_path and current_path.parent.is_dir()
            else self._settings_directory("firmware_dir")
        )
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Firmware für LTE-Cache auswählen",
            str(start),
            "Alle Dateien (*);;BIN-Dateien (*.bin)",
        )
        if file_name:
            self.cache_firmware.setText(file_name)
            self.settings.setValue("firmware_dir", str(Path(file_name).parent))
            self.settings.sync()
            self._buttons()

    def _check_for_updates(self, *, silent: bool) -> None:
        if self._release_check_running:
            return
        self._release_check_running = True
        self.release_check_btn.setEnabled(False)
        self.release_status.setStyleSheet("")
        self.release_status.setText("Prüfe GitHub Releases …")

        def work():
            try:
                value = release_check.fetch_latest_release(APP_VERSION)
            except Exception as error:
                self._update_signals.error.emit(str(error))
            else:
                self._update_signals.result.emit(value)

        threading.Thread(target=work, daemon=True).start()

    def _release_check_result(self, value: dict) -> None:
        self._release_check_running = False
        self.release_check_btn.setEnabled(True)
        tag = str(value.get("tag", "?"))
        self._latest_release_url = str(value.get("html_url") or release_check.UPDATE_RELEASES_URL)
        self.release_open_btn.setEnabled(True)
        if value.get("newer") is True:
            self.release_status.setStyleSheet(f"QLabel{{color:{YELLOW};font-weight:bold;}}")
            self.release_status.setText(
                f"Neue Version verfügbar: {tag} (installiert: v{APP_VERSION})."
            )
        else:
            self.release_status.setStyleSheet(f"QLabel{{color:{GREEN};}}")
            self.release_status.setText(
                f"Installierte Version v{APP_VERSION} ist aktuell. Letztes Release: {tag}."
            )

    def _release_check_error(self, message: str) -> None:
        self._release_check_running = False
        self.release_check_btn.setEnabled(True)
        self.release_open_btn.setEnabled(True)
        self._latest_release_url = release_check.UPDATE_RELEASES_URL
        self.release_status.setStyleSheet(f"QLabel{{color:{GRAY};}}")
        self.release_status.setText(
            "GitHub-Updateprüfung derzeit nicht möglich. Die Updater-Funktionen bleiben davon unberührt."
        )
        self._log("[Update-Prüfung] " + message)

    def _open_latest_release(self) -> None:
        QDesktopServices.openUrl(QUrl(self._latest_release_url))

    def _reset_flow(self, title: str, *, transfer_expected: bool = False):
        self._flow_steps.clear()
        self._flow_title = title
        self.progress.setValue(0)
        self.progress.setFormat(
            "Warte auf Firmwareübertragung …"
            if transfer_expected
            else "Keine Firmwareübertragung"
        )
        self.progress_text.setText(title)
        self._render_flow()

    def _set_step(self, key: str, level: str, text: str):
        self._flow_steps[key] = (level, text)
        self._render_flow()

    def _render_flow(self):
        if not hasattr(self, "flow_status"):
            return
        colors = {"ok": GREEN, "warn": YELLOW, "error": RED, "info": GRAY}
        lines = [f"<b>{escape(self._flow_title)}</b>"]
        if not self._flow_steps:
            lines.append(f'<span style="color:{GRAY};">● Noch keine Prüfschritte ausgeführt.</span>')
        else:
            for level, text in self._flow_steps.values():
                color = colors.get(level, GRAY)
                lines.append(
                    f'<span style="color:{color};"><b>●</b></span> {escape(text)}'
                )
        self.flow_status.setText("<br>".join(lines))

    @staticmethod
    def _records(output: str) -> list[dict]:
        records = []
        for line in output.splitlines():
            try:
                value = json.loads(line)
            except Exception:
                continue
            if isinstance(value, dict):
                records.append(value)
        return records

    @staticmethod
    def _record_phase(record: dict) -> str | None:
        hook = record.get("hook")
        if isinstance(hook, dict) and isinstance(hook.get("phase"), str):
            return hook["phase"]
        phase = record.get("phase")
        return phase if isinstance(phase, str) else None

    @classmethod
    def _has_phase(cls, records: list[dict], wanted: str) -> bool:
        return any(cls._record_phase(record) == wanted for record in records)

    @staticmethod
    def _has_event(records: list[dict], wanted: str) -> bool:
        return any(record.get("event") == wanted for record in records)

    @staticmethod
    def _same_version_seen(records: list[dict]) -> bool:
        for record in records:
            hook = record.get("hook")
            if isinstance(hook, dict) and hook.get("phase") == "same-version":
                return True
            if record.get("event") == "same-version-complete":
                return True
            if record.get("event") == "warning" and "Gleiche Firmware" in str(record.get("message", "")):
                return True
        return False

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _summary_record(output: str, event: str) -> dict | None:
        for record in reversed(MainWindow._records(output)):
            if record.get("event") == event:
                return record
        return None

    def _handle_plain_status(self, text: str):
        prefix = "[Windows-Sicherheitswrapper] "
        if not text.startswith(prefix):
            return
        message = text[len(prefix):].strip()
        if message.startswith("FEHLER:"):
            self._set_step("wrapper-error", "error", message)
        elif message.startswith("Vollanalyse:"):
            self._set_step(
                "full-preflight",
                "ok",
                "Full-Prüfung: Firmwareidentität, Größe und Hashes stimmen mit dem Manifest überein.",
            )
        elif "LTE-Cache-Firmware vor dem OTA gesichert" in message:
            self._set_step("cache-backup", "ok", "Vorhandene LTE-Cache-Firmware wurde zusätzlich gesichert.")
        elif "Vor dem OTA war keine Firmware" in message:
            self._set_step("cache-backup", "ok", "Ursprünglicher LTE-Cache war leer und wurde als Ausgangszustand dokumentiert.")
        elif "LTE-Cache-Firmware wiederhergestellt" in message:
            self._set_step("cache-restore", "ok", "Ursprüngliche LTE-Cache-Firmware wurde wiederhergestellt.")
        elif "leer" in message and "Cache-Zustand wiederhergestellt" in message:
            self._set_step("cache-restore", "ok", "Ursprünglicher leerer LTE-Cache-Zustand wurde wiederhergestellt.")
        elif "Update terminal erfolgreich" in message:
            self._set_step("wrapper-finish", "ok", "Windows-Sicherheitszustand wurde sauber abgeschlossen.")
        elif "nicht erfolgreich terminal beendet" in message:
            self._set_step("wrapper-finish", "warn", "Cache-Sicherung bleibt für einen möglichen zulässigen Recovery-Fall erhalten.")

    def _handle_preflight(self, record: dict):
        if "firmware_ok" in record:
            self._set_step(
                "preflight-firmware",
                "ok" if record.get("firmware_ok") is True else "error",
                "Firmwaredatei und Manifest sind konsistent."
                if record.get("firmware_ok") is True
                else "Firmwaredatei oder Manifestprüfung fehlgeschlagen.",
            )
        if "adb_state" in record:
            adb_ok = record.get("adb_state") == "device"
            self._set_step(
                "preflight-adb",
                "ok" if adb_ok else "error",
                "ADB-Verbindung zum LTE-Modem ist bereit."
                if adb_ok
                else f"ADB-Status ist nicht bereit: {record.get('adb_state')}",
            )
        if "service_binary_ok" in record:
            service_ok = record.get("service_binary_ok") is True
            self._set_step(
                "preflight-service",
                "ok" if service_ok else "error",
                "Geprüfter PHNIX-Originaldienst ist aktiv und unverändert."
                if service_ok
                else "PHNIX-Originaldienst stimmt nicht mit dem geprüften Build überein.",
            )
        watchdog_ok = bool(str(record.get("watchdog_pids", "")).strip())
        if "watchdog_pids" in record:
            self._set_step(
                "preflight-watchdogs",
                "ok" if watchdog_ok else "error",
                "Überwachungsdienste sind aktiv."
                if watchdog_ok
                else "Überwachungsdienste wurden nicht vollständig erkannt.",
            )
        if "gdb_present" in record or "httpd_present" in record:
            tools_ok = record.get("gdb_present") is True and record.get("httpd_present") is True
            self._set_step(
                "preflight-tools",
                "ok" if tools_ok else "error",
                "Benötigte Diagnose-/HTTP-Werkzeuge auf dem LTE-Modem sind vorhanden."
                if tools_ok
                else "Benötigte Werkzeuge auf dem LTE-Modem fehlen.",
            )
        ota_info = record.get("ota_info")
        if isinstance(ota_info, dict):
            crc_ok = ota_info.get("crc_ok") is True
            self._set_step(
                "preflight-ota-info",
                "ok" if crc_ok else "error",
                "OTA-Statusdatei ist gültig und CRC-geprüft."
                if crc_ok
                else "OTA-Statusdatei oder CRC ist ungültig.",
            )
        if "no_active_resume" in record:
            resume_ok = record.get("no_active_resume") is True
            self._set_step(
                "preflight-resume",
                "ok" if resume_ok else "error",
                "Kein offener Firmware-Transferzustand vorhanden."
                if resume_ok
                else "Es wurde ein offener Firmware-Transferzustand erkannt.",
            )
        if record.get("ok") is True:
            self._set_step("preflight-result", "ok", "Vorprüfung vollständig bestanden.")
        elif record.get("ok") is False:
            failures = record.get("failures")
            detail = ", ".join(str(item) for item in failures) if isinstance(failures, list) else "Details im Protokoll"
            self._set_step("preflight-result", "error", f"Vorprüfung fehlgeschlagen: {detail}")

    def _handle_phase(self, phase: str):
        mapping = {
            "verified": ("phase-verified", "ok", "Sicherheitsprüfungen bestanden."),
            "waiting-for-yield-loop": ("phase-yield", "warn", "Warte auf einen sicheren Sendepunkt im Originaldienst."),
            "c350-probe-attaching": ("phase-yield", "warn", "Warte auf einen sicheren Sendepunkt im Originaldienst."),
            "parser-injection": ("phase-start", "warn", "Updateauftrag wird kontrolliert an den Originaldienst übergeben."),
            "accepted": ("phase-accepted", "ok", "Originaldienst hat den Updateauftrag angenommen."),
            "c350-sent": ("phase-c350", "warn", "Firmwareangebot wurde an das Mainboard gesendet."),
            "c350": ("phase-c350", "warn", "Mainboard prüft Firmwarekennung und Version."),
            "c357": ("phase-c357", "ok", "Mainboard hat die Transfermetadaten angenommen."),
            "c5a8": ("phase-c5a8", "warn", "Firmwaredaten werden zum Mainboard übertragen."),
            "success-report": ("phase-success-report", "ok", "Mainboard meldet erfolgreichen Transferabschluss."),
            "success": ("phase-success", "ok", "Firmwareupdate wurde erfolgreich abgeschlossen."),
            "same-version": ("phase-same", "warn", "Gleiche Firmware erkannt – keine Firmwaredaten übertragen."),
            "c350-same-version": ("phase-same", "warn", "Gleiche Firmware erkannt – keine Firmwaredaten übertragen."),
        }
        item = mapping.get(phase)
        if item:
            self._set_step(*item)
            self.progress_text.setText(item[2])
            if phase in {"same-version", "c350-same-version"}:
                self.progress.setValue(0)
                self.progress.setFormat("Keine Übertragung – gleiche Firmware")

    def _handle_record(self, record: dict):
        event = record.get("event")
        if event == "preflight":
            self._handle_preflight(record)
        elif event == "helper-local-verified":
            self._set_step("helper-local", "ok", "Lokaler Update-Helfer wurde geprüft.")
        elif event == "helper-installed":
            self._set_step("helper-installed", "ok", "Update-Helfer wurde verifiziert auf das LTE-Modem übertragen.")
        elif event == "state-backed-up":
            self._set_step("state-backup", "ok", "OTA-Ausgangszustand wurde gesichert.")
        elif event == "firmware-staged":
            self._set_step("firmware-staged", "ok", "Firmware wurde auf dem LTE-Modem bereitgestellt.")
        elif event == "hook-start":
            self._set_step("hook-start", "warn", "Updateablauf gestartet – Mainboard-Reaktion wird überwacht.")
        elif event == "warning":
            message = str(record.get("message", "Warnung"))
            if "Gleiche Firmware" in message:
                message = "Gleiche Firmware erkannt – Update nicht erforderlich; keine Firmwaredaten übertragen."
            self._set_step("warning", "warn", message)
        elif event in {"guarded-hold", "manual-recovery-required", "error"}:
            message = str(record.get("message") or "Update wurde aus Sicherheitsgründen angehalten.")
            self._set_step("terminal-error", "error", message)
        elif event == "helper-removed":
            self._set_step("cleanup", "ok", "Temporärer Update-Helfer wurde wieder entfernt.")
        elif event == "hook-stopped":
            self._set_step("cleanup", "ok", "Temporärer Updatezustand wurde beendet.")
        elif event == "services-restored":
            ok = record.get("ok") is True
            self._set_step(
                "services-restored",
                "ok" if ok else "error",
                "Originaldienst, Watchdogs und Cloud/MQTT laufen wieder."
                if ok
                else "Originalbetrieb konnte nicht vollständig bestätigt werden.",
            )
        elif event == "original-state-released":
            self._set_step("original-state", "ok", "LTE-Modem befindet sich wieder im Originalzustand.")
        elif event == "dry-run-complete":
            self._set_step("dry-complete", "ok", "Dry-Run erfolgreich beendet – nichts wurde verändert.")
        elif event == "same-version-complete":
            self._set_step("same-complete", "ok", "Gleichversionstest sicher beendet – keine Firmware geschrieben.")
        elif event == "complete":
            self._set_step("update-complete", "ok", "Firmwareübertragung und Mainboard-Abschluss erfolgreich.")
            self.progress.setValue(100)
            self.progress.setFormat("100 % – Firmwareupdate abgeschlossen")

        phase = self._record_phase(record)
        if phase:
            self._handle_phase(phase)

        info = record.get("ota_info")
        if (
            isinstance(info, dict)
            and isinstance(info.get("offset"), int)
            and isinstance(info.get("length"), int)
            and info["length"] > 0
        ):
            offset = info["offset"]
            length = info["length"]
            percent = min(100, max(0, round(offset * 100 / length)))
            self.progress.setValue(percent)
            self.progress.setFormat(
                (f"{percent} % – {offset:,} / {length:,} Byte").replace(",", ".")
            )
            self.progress_text.setText("Firmwareübertragung läuft.")

    def _line(self, text):
        # Preserve the existing raw protocol and base parser exactly as before.
        super()._line(text)
        self._handle_plain_status(text)
        try:
            record = json.loads(text)
        except Exception:
            return
        if isinstance(record, dict):
            self._handle_record(record)

    def _backup_run(self):
        adb = self._require_adb()
        if not adb:
            return
        target = Path(self.backup_path.text().strip())
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.critical(self, "Backup", f"Backup-Ziel konnte nicht angelegt werden:\n{error}")
            return

        items = []
        if self.backup_fw.isChecked():
            items.append(("Firmware", "/cache/phnixIot_device_OTA", "phnixIot_device_OTA"))
        if self.backup_info.isChecked():
            items.append(("OTA_INFO", "/data/phnixIot_device_OTA_INFO", "phnixIot_device_OTA_INFO"))
        if self.backup_stat.isChecked():
            items.append(("Statistik", "/data/phnixIot_device_statisic", "phnixIot_device_statisic"))
        if self.backup_service.isChecked():
            items.append(("Originaldienst phnixIot4G", "/data/phnixIot4G", "phnixIot4G"))
        if not items:
            QMessageBox.information(self, "Backup", "Bitte mindestens eine Datei für das Backup auswählen.")
            return

        self.busy = True
        self._buttons()
        adb_env = self._adb_env()
        if adb_env:
            self._log("[Remote ADB] ADB_SERVER_SOCKET=" + adb_env["ADB_SERVER_SOCKET"])

        def work():
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            output: list[str] = []
            copied: list[dict] = []
            missing: list[dict] = []
            failed: list[dict] = []

            def run(command: list[str]) -> subprocess.CompletedProcess:
                command_text = "$ " + subprocess.list2cmdline(command)
                output.append(command_text)
                self.signals.line.emit(command_text)
                completed = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=flags,
                    env=self._process_env(),
                    check=False,
                )
                for line in completed.stdout.splitlines():
                    output.append(line)
                    self.signals.line.emit(line)
                return completed

            try:
                for label, remote, name in items:
                    probe = run([
                        str(adb),
                        "shell",
                        f"if [ -f '{remote}' ]; then echo PRESENT; else echo ABSENT; fi",
                    ])
                    state = probe.stdout.replace("\r", "").strip().splitlines()
                    state_value = state[-1].strip() if state else ""
                    if probe.returncode != 0:
                        failed.append({"label": label, "remote": remote, "reason": "ADB-Dateiprüfung fehlgeschlagen"})
                        continue
                    if state_value != "PRESENT":
                        missing.append({"label": label, "remote": remote})
                        warning = json.dumps(
                            {"event": "backup-missing", "label": label, "remote": remote},
                            ensure_ascii=False,
                        )
                        output.append(warning)
                        self.signals.line.emit(warning)
                        continue

                    destination = target / name
                    pull = run([str(adb), "pull", remote, str(destination)])
                    if pull.returncode == 0 and destination.is_file():
                        copied.append({"label": label, "remote": remote, "local": str(destination)})
                    else:
                        failed.append({"label": label, "remote": remote, "reason": "adb pull fehlgeschlagen"})

                summary = json.dumps(
                    {
                        "event": "backup-summary",
                        "copied": copied,
                        "missing": missing,
                        "failed": failed,
                        "target": str(target),
                    },
                    ensure_ascii=False,
                )
                output.append(summary)
                self.signals.line.emit(summary)
                self.signals.done.emit("backup", 0 if not failed else 2, "\n".join(output))
            except Exception as error:
                message = "[Backup-Prozessfehler] " + str(error)
                output.append(message)
                self.signals.line.emit(message)
                self.signals.done.emit("backup", -1, "\n".join(output))

        threading.Thread(target=work, daemon=True).start()

    def _manual_cache_copy(self):
        adb = self._require_adb()
        if not adb:
            return
        firmware = Path(self.cache_firmware.text().strip().strip('"'))
        if not firmware.is_file():
            QMessageBox.warning(self, "Firmware fehlt", "Bitte zuerst eine Firmwaredatei auswählen.")
            return

        size = firmware.stat().st_size
        if (
            QMessageBox.warning(
                self,
                "LTE-Firmware-Cache überschreiben",
                "Die ausgewählte Datei wird nach erfolgreicher SHA-256-Prüfung auf\n\n"
                f"{REMOTE_CACHE_FIRMWARE}\n\n"
                f"kopiert. Eine dort vorhandene Cache-Datei wird ersetzt.\n"
                f"Datei: {firmware.name}\nGröße: {size:,} Byte\n\n"
                "Dadurch wird kein Mainboard-Update gestartet. Fortfahren?".replace(",", "."),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return

        expected_sha256 = self._sha256_file(firmware)
        self.busy = True
        self._buttons()
        adb_env = self._adb_env()
        if adb_env:
            self._log("[Remote ADB] ADB_SERVER_SOCKET=" + adb_env["ADB_SERVER_SOCKET"])

        def work():
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            output: list[str] = []

            def run(command: list[str]) -> subprocess.CompletedProcess:
                command_text = "$ " + subprocess.list2cmdline(command)
                output.append(command_text)
                self.signals.line.emit(command_text)
                completed = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=flags,
                    env=self._process_env(),
                    check=False,
                )
                for line in completed.stdout.splitlines():
                    output.append(line)
                    self.signals.line.emit(line)
                return completed

            def finish(code: int, error: str | None = None):
                record = {
                    "event": "manual-cache-copy",
                    "ok": code == 0,
                    "local": str(firmware),
                    "remote": REMOTE_CACHE_FIRMWARE,
                    "size": size,
                    "sha256": expected_sha256,
                }
                if error:
                    record["error"] = error
                line = json.dumps(record, ensure_ascii=False)
                output.append(line)
                self.signals.line.emit(line)
                self.signals.done.emit("cache-copy", code, "\n".join(output))

            try:
                push = run([str(adb), "push", str(firmware), REMOTE_CACHE_STAGE])
                if push.returncode != 0:
                    finish(2, "Übertragung der temporären Datei fehlgeschlagen")
                    return

                verify_stage = run([
                    str(adb),
                    "shell",
                    f"sha256sum '{REMOTE_CACHE_STAGE}' | awk '{{print $1}}'",
                ])
                remote_stage_hash = verify_stage.stdout.replace("\r", "").strip().splitlines()
                remote_stage_hash = remote_stage_hash[-1].strip().lower() if remote_stage_hash else ""
                if verify_stage.returncode != 0 or remote_stage_hash != expected_sha256.lower():
                    run([str(adb), "shell", f"rm -f '{REMOTE_CACHE_STAGE}'"])
                    finish(2, "SHA-256 der temporär übertragenen Datei stimmt nicht")
                    return

                promote = run([
                    str(adb),
                    "shell",
                    f"mv '{REMOTE_CACHE_STAGE}' '{REMOTE_CACHE_FIRMWARE}' && sync && "
                    f"sha256sum '{REMOTE_CACHE_FIRMWARE}' | awk '{{print $1}}'",
                ])
                remote_final_hash = promote.stdout.replace("\r", "").strip().splitlines()
                remote_final_hash = remote_final_hash[-1].strip().lower() if remote_final_hash else ""
                if promote.returncode != 0 or remote_final_hash != expected_sha256.lower():
                    finish(2, "Finale SHA-256-Prüfung am Originalpfad fehlgeschlagen")
                    return

                finish(0)
            except Exception as error:
                finish(-1, str(error))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, op, code, output):
        if op == "backup":
            super()._done("handled-result", code, output)
            summary = self._summary_record(output, "backup-summary")
            if not summary:
                QMessageBox.critical(
                    self,
                    "Backup fehlgeschlagen",
                    "Das Backup konnte nicht vollständig ausgewertet werden. Details stehen im Protokoll.",
                )
                return

            copied = summary.get("copied") if isinstance(summary.get("copied"), list) else []
            missing = summary.get("missing") if isinstance(summary.get("missing"), list) else []
            failed = summary.get("failed") if isinstance(summary.get("failed"), list) else []
            lines = [f"Gesichert: {len(copied)} Datei(en)."]
            if copied:
                lines.extend(f"  ✓ {item.get('label', '?')}" for item in copied if isinstance(item, dict))
            if missing:
                lines.append("\nNicht auf dem LTE-Modem vorhanden:")
                lines.extend(
                    f"  • {item.get('label', '?')}: {item.get('remote', '?')}"
                    for item in missing
                    if isinstance(item, dict)
                )
            if failed:
                lines.append("\nFehlgeschlagen:")
                lines.extend(
                    f"  • {item.get('label', '?')}: {item.get('reason', 'unbekannter Fehler')}"
                    for item in failed
                    if isinstance(item, dict)
                )
            lines.append(f"\nZielordner:\n{summary.get('target', self.backup_path.text())}")
            text = "\n".join(lines)
            if failed or code != 0:
                QMessageBox.critical(self, "Backup teilweise fehlgeschlagen", text)
            elif missing:
                QMessageBox.warning(self, "Backup abgeschlossen mit Hinweis", text)
            else:
                QMessageBox.information(self, "Backup vollständig", text)
            return

        if op == "cache-copy":
            super()._done("handled-result", code, output)
            result = self._summary_record(output, "manual-cache-copy")
            if code == 0 and result and result.get("ok") is True:
                QMessageBox.information(
                    self,
                    "Firmware in LTE-Cache kopiert",
                    "Die Firmwaredatei wurde erfolgreich übertragen und per SHA-256 geprüft.\n\n"
                    f"Ziel: {REMOTE_CACHE_FIRMWARE}\n"
                    f"SHA-256: {result.get('sha256', '?')}\n\n"
                    "Es wurde kein OTA gestartet und nichts an das Mainboard gesendet.",
                )
            else:
                detail = result.get("error") if isinstance(result, dict) else None
                QMessageBox.critical(
                    self,
                    "Kopieren in LTE-Cache fehlgeschlagen",
                    "Die Firmwaredatei wurde nicht sicher am Originalpfad bestätigt."
                    + (f"\n\n{detail}" if detail else "")
                    + "\n\nDetails stehen im Protokoll.",
                )
            return

        if op not in {"dry", "update", "restore", "same"}:
            super()._done(op, code, output)
            return

        # Let the base class perform generic cleanup/logging without its technical Exit-code popup.
        super()._done("handled-result", code, output)
        records = self._records(output)

        if op == "dry":
            if code == 0 and self._has_event(records, "dry-run-complete"):
                self._flow_title = "Dry-Run erfolgreich"
                self._set_step("dry-result", "ok", "Alle Vorprüfungen bestanden. LTE-Modem und Mainboard wurden nicht verändert.")
                QMessageBox.information(
                    self,
                    "Dry-Run erfolgreich",
                    "Vorprüfung erfolgreich.\n\nAlle Sicherheitsprüfungen wurden bestanden. "
                    "Es wurde nichts am LTE-Modem oder Mainboard verändert.",
                )
            else:
                self._flow_title = "Dry-Run fehlgeschlagen"
                self._set_step("dry-result", "error", "Vorprüfung fehlgeschlagen – Update nicht starten.")
                QMessageBox.critical(
                    self,
                    "Dry-Run fehlgeschlagen",
                    "Die Vorprüfung ist fehlgeschlagen. Das Firmwareupdate wurde nicht gestartet.\n\n"
                    "Details stehen im Protokoll.",
                )
            self._render_flow()
            return

        if op == "update":
            same = self._same_version_seen(records)
            guarded = self._has_event(records, "guarded-hold") or self._has_event(records, "manual-recovery-required")
            completed = self._has_event(records, "complete") or self._has_phase(records, "success")
            if code == 0 and same:
                self._flow_title = "Update nicht durchgeführt – gleiche Firmware"
                self._set_step("update-result", "warn", "Mainboard hat die bereits installierte Firmware erkannt und sicher abgelehnt.")
                self._set_step("update-no-write", "ok", "Es wurden keine Firmwaredaten übertragen.")
                QMessageBox.information(
                    self,
                    "Update nicht erforderlich",
                    "Das Firmwareupdate wurde nicht durchgeführt, weil die gleiche Firmware bereits installiert ist.\n\n"
                    "Es wurden keine Firmwaredaten übertragen. Der Originalbetrieb wurde wiederhergestellt.",
                )
            elif code == 0 and completed:
                self._flow_title = "Firmwareupdate erfolgreich"
                self._set_step("update-result", "ok", "Firmwareupdate vollständig und sicher abgeschlossen.")
                self.progress.setValue(100)
                self.progress.setFormat("100 % – Firmwareupdate abgeschlossen")
                QMessageBox.information(
                    self,
                    "Firmwareupdate erfolgreich",
                    "Das Firmwareupdate wurde vollständig abgeschlossen.\n\n"
                    "Der Originalbetrieb wurde anschließend geprüft.",
                )
            elif guarded:
                self._flow_title = "Update sicher angehalten"
                self._set_step("update-result", "error", "Guarded Hold – keine weiteren Updatebefehle ausführen.")
                QMessageBox.critical(
                    self,
                    "Update sicher angehalten",
                    "Der Controller hat einen unerwarteten Zustand erkannt und den Ablauf geschützt angehalten.\n\n"
                    "Keine weiteren Updatebefehle ausführen und Wärmepumpe/LTE-Modem nicht stromlos machen. "
                    "Details im Protokoll sichern.",
                )
            else:
                self._flow_title = "Firmwareupdate fehlgeschlagen"
                self._set_step("update-result", "error", "Firmwareupdate wurde wegen eines Fehlers abgebrochen.")
                QMessageBox.critical(
                    self,
                    "Firmwareupdate fehlgeschlagen",
                    "Das Firmwareupdate wurde nicht erfolgreich abgeschlossen.\n\n"
                    f"Technischer Exit-Code: {code}\nDetails stehen im Protokoll.",
                )
            self._render_flow()
            return

        if op == "same":
            same = self._same_version_seen(records)
            if code == 0 and same:
                self._flow_title = "Gleichversionstest erfolgreich"
                self._set_step("same-result", "ok", "Gleiche Firmware sicher erkannt und ohne Datenübertragung beendet.")
                QMessageBox.information(
                    self,
                    "Gleichversionstest erfolgreich",
                    "Das Mainboard hat die bereits installierte Firmware erwartungsgemäß erkannt.\n\n"
                    "Es wurden keine Firmwaredaten übertragen.",
                )
            else:
                self._flow_title = "Gleichversionstest fehlgeschlagen"
                self._set_step("same-result", "error", "Gleichversionstest wurde nicht sicher abgeschlossen.")
                QMessageBox.critical(
                    self,
                    "Gleichversionstest fehlgeschlagen",
                    "Der Gleichversionstest wurde nicht sicher abgeschlossen. Details stehen im Protokoll.",
                )
            self._render_flow()
            return

        if op == "restore":
            if code == 0:
                self._flow_title = "Wiederherstellung erfolgreich"
                self._set_step("restore-result", "ok", "Originalzustand wurde erfolgreich wiederhergestellt und geprüft.")
                QMessageBox.information(
                    self,
                    "Wiederherstellung erfolgreich",
                    "Der zulässige Wiederherstellungspfad wurde erfolgreich abgeschlossen. "
                    "Der Originalzustand wurde anschließend geprüft.",
                )
            else:
                self._flow_title = "Wiederherstellung fehlgeschlagen"
                self._set_step("restore-result", "error", "Originalzustand konnte nicht vollständig wiederhergestellt werden.")
                QMessageBox.critical(
                    self,
                    "Wiederherstellung fehlgeschlagen",
                    "Die Wiederherstellung wurde nicht erfolgreich abgeschlossen. Details stehen im Protokoll.",
                )
            self._render_flow()

    def _dry(self):
        self._reset_flow("Vorprüfung / Dry-Run läuft", transfer_expected=False)
        super()._dry()

    def _update_run(self):
        self._reset_flow("Firmwareupdate wird vorbereitet", transfer_expected=True)
        super()._update_run()
        if not self.busy:
            self._flow_title = "Firmwareupdate nicht gestartet"
            self._set_step("not-started", "info", "Start wurde abgebrochen oder nicht bestätigt.")

    def _same(self):
        self._reset_flow("Gleichversionstest wird vorbereitet", transfer_expected=False)
        super()._same()

    def _buttons(self):
        super()._buttons()
        if hasattr(self, "cache_copy_btn"):
            firmware_ready = Path(self.cache_firmware.text().strip().strip('"')).is_file()
            self.cache_copy_btn.setEnabled(not self.busy and self._adb_ready() and firmware_ready)

    def closeEvent(self, event):
        self._persist_settings()
        super().closeEvent(event)


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
