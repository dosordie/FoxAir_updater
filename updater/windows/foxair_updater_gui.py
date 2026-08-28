from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QStandardPaths, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

APP_VERSION = "0.3.3"
ADB_URL = "https://developer.android.com/tools/releases/platform-tools?hl=de#downloads"
HOWTO_URL = "https://github.com/dosordie/FoxAir_updater/blob/main/docs/HowTo/firmware_backup_lte.md"
MODEM_DRIVER_URL = "https://files.waveshare.com/upload/2/24/SIMCOM_Windows_USB_Drivers_V1.0.2.zip"


def root_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def backend_dir() -> Path:
    packaged = root_dir() / "backend"
    return packaged if packaged.is_dir() else root_dir()


def backend_python() -> Path:
    packaged = root_dir() / "runtime" / "python.exe"
    return packaged if packaged.is_file() else Path(sys.executable)


def data_dir() -> Path:
    value = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
    path = Path(value) if value else Path.home() / ".foxair-updater"
    path.mkdir(parents=True, exist_ok=True)
    return path


class Signals(QObject):
    line = Signal(str)
    done = Signal(str, int, str)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("FoxAir", "FoxAir Updater")
        self.signals = Signals()
        self.signals.line.connect(self._line)
        self.signals.done.connect(self._done)

        self.busy = False
        self.pending_after_reconnect = False
        self.ota_monitoring_lost = False
        self.pending_manifest_output: Path | None = None

        self.controller = backend_dir() / "tools/phnix_ota/phnix_local_ota_controller.py"
        self.manifest_tool = backend_dir() / "tools/phnix_ota/create_firmware_manifest.py"
        self.state_dir = data_dir() / "phnix-ota-state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.setWindowTitle(f"FoxAir Updater {APP_VERSION} – EXPERIMENTELL")
        self.resize(1100, 780)
        icon = root_dir() / "app_icon.ico"
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))

        self._ui()
        self._load()
        self._buttons()

    def _ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)

        warning = QLabel(
            "<b>EXPERIMENTELL – echter Versionswechsel noch nicht live validiert.</b><br>"
            "Bisher wurde real nur V3.3 → V3.3 getestet; das Mainboard hat die gleiche "
            "Version erwartungsgemäß abgelehnt. Nutzung auf eigenes Risiko."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "QLabel{background:#fff1e8;border:2px solid #c84b00;padding:9px}"
        )
        layout.addWidget(warning)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._connection(), "Verbindung")
        self.tabs.addTab(self._backup(), "Backup")
        self.tabs.addTab(self._update(), "Firmware Update")
        self.tabs.addTab(self._manifest(), "Manifest")
        self.tabs.addTab(self._status(), "Status / Recovery")
        self.tabs.addTab(self._advanced(), "Erweitert")
        layout.addWidget(self.tabs)

        row = QHBoxLayout()
        row.addWidget(QLabel("<b>Protokoll</b>"))
        row.addStretch()
        clear_button = QPushButton("Protokoll leeren")
        clear_button.clicked.connect(self._clear_log)
        row.addWidget(clear_button)
        save_button = QPushButton("Log speichern…")
        save_button.clicked.connect(self._save_log)
        row.addWidget(save_button)
        layout.addLayout(row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)
        self.setCentralWidget(central)

    def _connection(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        row = QHBoxLayout()
        button = QPushButton("SIMCom USB-Treiber")
        button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(MODEM_DRIVER_URL)))
        row.addWidget(button)
        button = QPushButton("Android Platform Tools")
        button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ADB_URL)))
        row.addWidget(button)
        button = QPushButton("LTE-/USB-Anleitung")
        button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(HOWTO_URL)))
        row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("adb.exe Pfad:"))
        self.adb = QLineEdit()
        self.adb.setPlaceholderText(r"C:\platform-tools\adb.exe")
        self.adb.editingFinished.connect(self._adb_changed)
        button = QPushButton("adb.exe auswählen…")
        button.clicked.connect(self._browse_adb)
        row.addWidget(self.adb, 1)
        row.addWidget(button)
        layout.addLayout(row)

        layout.addWidget(QLabel("<hr>"))

        layout.addWidget(QLabel("<b>ADB-Verbindungsmodus</b>"))
        row = QHBoxLayout()
        self.adb_local = QRadioButton("Lokal – LTE-Modem direkt an diesem Windows-PC")
        self.adb_remote = QRadioButton("Remote – ADB-Server auf Raspberry Pi")
        self.adb_local.toggled.connect(self._remote_changed)
        self.adb_remote.toggled.connect(self._remote_changed)
        row.addWidget(self.adb_local)
        row.addWidget(self.adb_remote)
        row.addStretch()
        layout.addLayout(row)

        description = QLabel(
            "<b>Lokal:</b> Das USB-Modem hängt direkt am Windows-Rechner.<br>"
            "<b>Remote:</b> Das USB-Modem hängt z. B. am Raspberry Pi; Windows verwendet "
            "dessen ADB-Server.<br>Auch im Remote-Modus wird lokal eine "
            "<code>adb.exe</code> als Client benötigt."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        remote_form_widget = QWidget()
        remote_form = QFormLayout(remote_form_widget)
        self.remote_host = QLineEdit()
        self.remote_host.setPlaceholderText("192.168.1.100")
        self.remote_host.textChanged.connect(self._remote_changed)
        remote_form.addRow("Raspberry-Pi-IP:", self.remote_host)
        self.remote_port = QSpinBox()
        self.remote_port.setRange(1, 65535)
        self.remote_port.setValue(5038)
        self.remote_port.valueChanged.connect(self._remote_changed)
        remote_form.addRow("ADB-Server-Port:", self.remote_port)
        layout.addWidget(remote_form_widget)

        remote_help_frame = QFrame()
        remote_help_frame.setObjectName("remoteAdbHelp")
        remote_help_frame.setStyleSheet(
            "QFrame#remoteAdbHelp{background:#f7f8fa;border:1px solid #d0d5dd;"
            "border-radius:4px;padding:8px;}"
        )
        remote_help_layout = QVBoxLayout(remote_help_frame)
        self.remote_help = QLabel()
        self.remote_help.setWordWrap(True)
        remote_help_layout.addWidget(self.remote_help)
        layout.addWidget(remote_help_frame)

        self.adb_state = QLabel("ADB noch nicht geprüft.")
        self.adb_state.setWordWrap(True)
        layout.addWidget(self.adb_state)

        row = QHBoxLayout()
        self.adb_check = QPushButton("ADB prüfen")
        self.adb_check.clicked.connect(self._check_adb)
        self.adb_reconnect = QPushButton("ADB reconnect")
        self.adb_reconnect.clicked.connect(self._reconnect)
        row.addWidget(self.adb_check)
        row.addWidget(self.adb_reconnect)
        row.addStretch()
        layout.addLayout(row)

        note = QLabel(
            "ADB wird nicht mitgeliefert. Auch im Remote-Modus wird lokal eine "
            "adb.exe als Client benötigt; nur der ADB-Server und das USB-Modem "
            "laufen auf dem Raspberry Pi."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        return widget

    def _backup(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        row = QHBoxLayout()
        self.backup_path = QLineEdit()
        button = QPushButton("Zielordner…")
        button.clicked.connect(self._browse_backup)
        open_button = QPushButton("Zielordner öffnen")
        open_button.clicked.connect(self._open_backup_folder)
        row.addWidget(self.backup_path, 1)
        row.addWidget(button)
        row.addWidget(open_button)
        layout.addLayout(row)

        self.backup_fw = QCheckBox("Firmware")
        self.backup_fw.setChecked(True)
        self.backup_info = QCheckBox("OTA_INFO")
        self.backup_info.setChecked(True)
        self.backup_stat = QCheckBox("Statistik")
        self.backup_stat.setChecked(True)
        self.backup_service = QCheckBox("Originaldienst phnixIot4G")
        for item in (self.backup_fw, self.backup_info, self.backup_stat, self.backup_service):
            layout.addWidget(item)

        details = QLabel(
            "<b>Firmware:</b> aktuell im LTE-Cache vorhandene OTA-/Firmwaredatei<br>"
            "<b>OTA_INFO:</b> persistenter OTA-/Resume-Zustand des LTE-Dienstes<br>"
            "<b>Statistik:</b> persistente Betriebs-, Kommunikations-, Reset- und OTA-Zähler<br>"
            "<b>Originaldienst phnixIot4G:</b> originale ausführbare PHNIX-LTE-Programmdatei"
        )
        details.setWordWrap(True)
        layout.addWidget(details)

        self.backup_button = QPushButton("Backup erstellen")
        self.backup_button.clicked.connect(self._backup_run)
        layout.addWidget(self.backup_button)
        note = QLabel(
            "<b>Read-only:</b> Das Backup erfolgt ausschließlich per <code>adb pull</code> "
            "und verändert nichts am LTE-Modem oder Mainboard."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        return widget

    def _update(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        row = QHBoxLayout()
        self.update_manifest = QLineEdit()
        self.update_manifest.textChanged.connect(self._manifest_summary)
        button = QPushButton("Manifest…")
        button.clicked.connect(lambda: self._pick_manifest(self.update_manifest))
        row.addWidget(self.update_manifest, 1)
        row.addWidget(button)
        layout.addLayout(row)

        self.summary = QLabel("Noch kein Manifest ausgewählt.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.progress_text = QLabel("Kein Update aktiv.")
        progress_font = self.progress_text.font()
        progress_font.setPointSize(max(12, progress_font.pointSize() + 2))
        progress_font.setBold(True)
        self.progress_text.setFont(progress_font)
        layout.addWidget(self.progress_text)
        self.progress = QProgressBar()
        self.progress.setMinimumHeight(42)
        layout.addWidget(self.progress)
        self.ota_reattach_btn = QPushButton("ADB neu verbinden / OTA-Status prüfen")
        self.ota_reattach_btn.clicked.connect(self._reattach_ota)
        self.ota_reattach_btn.setVisible(False)
        layout.addWidget(self.ota_reattach_btn)
        self.dry = QPushButton("Vorprüfung / Dry-Run")
        self.dry.clicked.connect(self._dry)
        layout.addWidget(self.dry)
        self.risk = QCheckBox(
            "Risiko eines noch nicht live validierten Versionswechsels verstanden."
        )
        self.risk.toggled.connect(self._buttons)
        layout.addWidget(self.risk)
        self.update_btn = QPushButton("FIRMWAREUPDATE STARTEN")
        self.update_btn.clicked.connect(self._update_run)
        layout.addWidget(self.update_btn)
        layout.addStretch()
        return widget

    def _status(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.status_btn = QPushButton("Originalzustand prüfen")
        self.status_btn.clicked.connect(self._status_run)
        layout.addWidget(self.status_btn)
        check_note = QLabel(
            "<b>Read-only-Prüfung:</b> Prüft das LTE-Modem auf normalen Originalbetrieb: "
            "Originaldienst läuft, Programmdatei/SHA stimmt, kein Debugger, keine lokale "
            "OTA-Injection und keine Cloud-Sperre, Watchdogs laufen, MQTT/Cloud ist wieder "
            "verbunden und temporärer lokaler OTA-Zustand ist bereinigt. Es wird nichts verändert."
        )
        check_note.setWordWrap(True)
        layout.addWidget(check_note)
        self.status_text = QLabel("Noch kein Statuscheck.")
        self.status_text.setWordWrap(True)
        layout.addWidget(self.status_text)
        note = QLabel(
            "<b>Kontrollierter Recoverypfad:</b> Die Wiederherstellung ist nur vor einem "
            "begonnenen C5A8-Firmwaretransfer zulässig. Sobald C5A8 begonnen hat, ist das "
            "automatische Restore absichtlich gesperrt; ab dem ersten C5A8 bleibt der originale "
            "PHNIX-Dienst autoritativ. C36E Status 3 und ein fehlendes C37B/3 sind ausdrücklich "
            "keine sicheren Stopp- oder Restorepunkte."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.restore_btn = QPushButton("Originalzustand wiederherstellen")
        self.restore_btn.clicked.connect(self._restore)
        layout.addWidget(self.restore_btn)
        layout.addStretch()
        return widget

    def _manifest(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        explanation = QLabel(
            "<h3>Was ist das Manifest?</h3>"
            "Das Manifest beschreibt exakt die Firmwaredatei, die an das Mainboard übertragen "
            "werden soll. Es definiert Software-/Produktcode, Firmware-/Display-Version, "
            "Ziel/SSID, Dateigröße, MD5, SHA256 und die zugehörige Firmwaredatei.<br><br>"
            "<h3>Warum wird es benötigt?</h3>"
            "Es verbindet <b>Firmwaredatei + erkannte Firmwareidentität + kryptografische "
            "Prüfsummen</b> zu einem eindeutig überprüfbaren Updatepaket. Vor dem Update werden "
            "Dateizuordnung, Größe, MD5, SHA256, Softwarecode, angebotene Version und "
            "Mainboard-Ziel geprüft.<br><br>"
            "<b>Empfohlener Weg (Full):</b> 1. Originale Firmwaredatei auswählen, "
            "2. „Manifest automatisch erzeugen“ wählen, 3. die automatische Analyse und "
            "Eintragung der Werte/Prüfsummen abwarten, 4. das Manifest unter „Firmware Update“ "
            "auswählen.<br><br><b>Das Manifest verändert die Firmwaredatei NICHT.</b> Der manuelle "
            "Fallback ist nur vorgesehen, wenn die automatische Analyse nicht möglich ist und "
            "alle Werte sicher bekannt sind."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        row = QHBoxLayout()
        self.firmware = QLineEdit()
        button = QPushButton("Firmware…")
        button.clicked.connect(self._pick_firmware)
        row.addWidget(QLabel("Firmware:"))
        row.addWidget(self.firmware, 1)
        row.addWidget(button)
        layout.addLayout(row)

        auto_note = QLabel(
            "<b>Empfohlen:</b> Die Full-Variante analysiert die originale Firmwaredatei selbst, "
            "liest Software-Code und Version aus dem Image und berechnet die übrigen Manifestfelder. "
            "Die Firmwaredatei muss keine .bin-Endung besitzen und wird nicht verändert."
        )
        auto_note.setWordWrap(True)
        layout.addWidget(auto_note)

        row = QHBoxLayout()
        self.manifest_preview_btn = QPushButton("Vorschau aus Firmware (Full / Show)")
        self.manifest_preview_btn.clicked.connect(self._manifest_preview_full)
        row.addWidget(self.manifest_preview_btn)
        self.manifest_full_btn = QPushButton("Manifest automatisch erzeugen (Full)")
        self.manifest_full_btn.clicked.connect(self._manifest_full)
        row.addWidget(self.manifest_full_btn)
        row.addStretch()
        layout.addLayout(row)

        self.manifest_preview = QPlainTextEdit()
        self.manifest_preview.setReadOnly(True)
        self.manifest_preview.setPlaceholderText(
            "Hier erscheint die Full-/Show-Vorschau des erzeugten Manifests."
        )
        self.manifest_preview.setMaximumHeight(220)
        layout.addWidget(self.manifest_preview)

        fallback = QLabel(
            "<b>Fallback / manuell:</b> Nur verwenden, wenn die automatische Firmwareanalyse "
            "nicht möglich ist und die Werte sicher bekannt sind."
        )
        fallback.setWordWrap(True)
        layout.addWidget(fallback)

        form_widget = QWidget()
        form = QFormLayout(form_widget)
        self.sw_code = QLineEdit()
        self.sw_code.setPlaceholderText("82400644")
        form.addRow("Software Code:", self.sw_code)
        self.display_ver = QLineEdit()
        self.display_ver.setPlaceholderText("V3.4")
        form.addRow("Display-Version:", self.display_ver)
        self.ssid = QLineEdit()
        self.ssid.setText("0063")
        form.addRow("Target SSID:", self.ssid)
        layout.addWidget(form_widget)

        self.manifest_btn = QPushButton("Manifest manuell erzeugen (Fallback)")
        self.manifest_btn.clicked.connect(self._manifest_run)
        layout.addWidget(self.manifest_btn)
        layout.addStretch()
        return widget

    def _advanced(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addStretch()
        return widget

    def _load(self):
        saved = str(self.settings.value("adb", "") or "")
        found = Path(saved) if saved and Path(saved).is_file() else self._find_adb()
        if found:
            self.adb.setText(str(found))
        self.backup_path.setText(
            str(self.settings.value("backup", Path.home() / "FoxAir_LTE_Backup"))
        )
        remote = str(self.settings.value("adb_mode", "local")) == "remote"
        self.adb_remote.setChecked(remote)
        self.adb_local.setChecked(not remote)
        self.remote_host.setText(str(self.settings.value("remote_host", "") or ""))
        try:
            port = int(self.settings.value("remote_port", 5038))
        except (TypeError, ValueError):
            port = 5038
        self.remote_port.setValue(port)
        self._remote_changed()

    def _find_adb(self):
        candidates = []
        found = shutil.which("adb")
        if found:
            candidates.append(Path(found))
        if os.environ.get("LOCALAPPDATA"):
            candidates.append(Path(os.environ["LOCALAPPDATA"]) / "Android/Sdk/platform-tools/adb.exe")
        candidates += [Path.home() / "platform-tools/adb.exe", Path(r"C:\platform-tools\adb.exe")]
        return next((path for path in candidates if path.is_file()), None)

    def _adb_path(self):
        value = self.adb.text().strip().strip('"')
        path = Path(value) if value else None
        return path if path and path.is_file() else None

    def _adb_changed(self):
        self.settings.setValue("adb", self.adb.text().strip().strip('"'))
        self._buttons()

    def _remote_changed(self, *args):
        remote = hasattr(self, "adb_remote") and self.adb_remote.isChecked()
        if hasattr(self, "remote_host"):
            self.remote_host.setEnabled(remote)
            self.remote_port.setEnabled(remote)
            self.settings.setValue("adb_mode", "remote" if remote else "local")
            self.settings.setValue("remote_host", self.remote_host.text().strip())
            self.settings.setValue("remote_port", self.remote_port.value())
            port = self.remote_port.value()
            if remote:
                self.remote_help.setText(
                    "<b>Raspberry Pi für Remote ADB:</b><br>"
                    "<code>adb kill-server</code><br>"
                    f"<code>adb -a -P {port} nodaemon server</code><br>"
                    "Der Befehl bleibt im Vordergrund. Zum Beenden auf dem Raspberry Pi "
                    "<b>Strg+C</b> drücken. Nur kurzfristig in einem vertrauenswürdigen LAN verwenden."
                )
            else:
                self.remote_help.setText(
                    "Im lokalen Modus wird der normale ADB-Server auf diesem Windows-PC verwendet."
                )
        self._buttons()

    def _adb_env(self) -> dict[str, str]:
        if not self.adb_remote.isChecked():
            return {}
        host = self.remote_host.text().strip()
        if not host:
            return {}
        return {"ADB_SERVER_SOCKET": f"tcp:{host}:{self.remote_port.value()}"}

    def _adb_ready(self) -> bool:
        if self._adb_path() is None:
            return False
        if self.adb_remote.isChecked() and not self.remote_host.text().strip():
            return False
        return True

    def _browse_adb(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "adb.exe auswählen", str(Path.home()), "ADB (adb.exe)"
        )
        if file_name:
            self.adb.setText(file_name)
            self._adb_changed()

    def _browse_backup(self):
        directory = QFileDialog.getExistingDirectory(self, "Backup-Ziel", self.backup_path.text())
        if directory:
            self.backup_path.setText(directory)
            self.settings.setValue("backup", directory)

    def _open_backup_folder(self):
        value = self.backup_path.text().strip()
        target = Path(value) if value else Path.home() / "FoxAir_LTE_Backup"
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.critical(self, "Zielordner", f"Zielordner konnte nicht angelegt werden:\n{error}")
            return
        self.backup_path.setText(str(target))
        self.settings.setValue("backup", str(target))
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve()))):
            QMessageBox.warning(self, "Zielordner", "Zielordner konnte nicht im Explorer geöffnet werden.")

    def _pick_manifest(self, field):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Manifest auswählen", str(Path.home()), "Manifest (*.json)"
        )
        if file_name:
            field.setText(file_name)

    def _pick_firmware(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Firmware auswählen",
            str(Path.home()),
            "Alle Dateien (*);;BIN-Dateien (*.bin)",
        )
        if file_name:
            self.firmware.setText(file_name)
            self.manifest_preview.clear()
            self._buttons()

    def _require_adb(self):
        path = self._adb_path()
        if not path:
            QMessageBox.warning(
                self,
                "ADB fehlt",
                "Bitte zuerst adb.exe auswählen oder über den offiziellen Link herunterladen.",
            )
            self.tabs.setCurrentIndex(0)
            return None
        if self.adb_remote.isChecked() and not self.remote_host.text().strip():
            QMessageBox.warning(self, "Remote ADB", "Bitte die IP-Adresse des Raspberry Pi eintragen.")
            self.tabs.setCurrentIndex(0)
            return None
        return path

    def _process_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        env.pop("ADB_SERVER_SOCKET", None)
        env.update(self._adb_env())
        return env

    def _run(self, op, command, cwd=None):
        if self.busy:
            return
        self.busy = True
        self._buttons()
        adb_env = self._adb_env()
        if adb_env:
            self._log("[Remote ADB] ADB_SERVER_SOCKET=" + adb_env["ADB_SERVER_SOCKET"])
        self._log("$ " + subprocess.list2cmdline([str(item) for item in command]))

        def work():
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            output = []
            try:
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=flags,
                    env=self._process_env(),
                )
                for line in process.stdout or []:
                    line = line.rstrip("\r\n")
                    output.append(line)
                    self.signals.line.emit(line)
                self.signals.done.emit(op, process.wait(), "\n".join(output))
            except Exception as error:
                self.signals.line.emit("[Prozessfehler] " + str(error))
                self.signals.done.emit(op, -1, str(error))

        threading.Thread(target=work, daemon=True).start()

    def _run_sequence(self, op, commands, cwd=None):
        """Run commands directly and sequentially without cmd.exe quoting/parsing."""
        if self.busy:
            return
        self.busy = True
        self._buttons()
        adb_env = self._adb_env()
        if adb_env:
            self._log("[Remote ADB] ADB_SERVER_SOCKET=" + adb_env["ADB_SERVER_SOCKET"])

        def work():
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            output = []
            try:
                for command in commands:
                    self.signals.line.emit(
                        "$ " + subprocess.list2cmdline([str(item) for item in command])
                    )
                    process = subprocess.Popen(
                        command,
                        cwd=cwd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        creationflags=flags,
                        env=self._process_env(),
                    )
                    for line in process.stdout or []:
                        line = line.rstrip("\r\n")
                        output.append(line)
                        self.signals.line.emit(line)
                    code = process.wait()
                    if code != 0:
                        self.signals.done.emit(op, code, "\n".join(output))
                        return
                self.signals.done.emit(op, 0, "\n".join(output))
            except Exception as error:
                self.signals.line.emit("[Prozessfehler] " + str(error))
                self.signals.done.emit(op, -1, str(error))

        threading.Thread(target=work, daemon=True).start()

    def _backend(self, op, args):
        adb = self._require_adb()
        if not adb:
            return
        command = [
            str(backend_python()),
            str(self.controller),
            "--adb",
            str(adb),
            "--output",
            "json",
            "--no-color",
            *args,
        ]
        self._run(op, command, str(backend_dir()))

    def _manifest_command(self, *, full: bool, show: bool, output: Path | None = None):
        firmware = Path(self.firmware.text().strip())
        if not firmware.is_file():
            QMessageBox.warning(self, "Firmware fehlt", "Bitte zuerst eine Firmwaredatei auswählen.")
            return None
        command = [str(backend_python()), str(self.manifest_tool), "--firmware", str(firmware)]
        if full:
            command.append("--full")
        if show:
            command.append("--show")
        elif output is not None:
            command += ["--output", str(output)]
        return command

    def _line(self, text):
        self._log(text)
        try:
            record = json.loads(text)
        except Exception:
            return
        if not isinstance(record, dict):
            return
        event = record.get("event")
        if event in ("guarded-hold", "manual-recovery-required"):
            QMessageBox.critical(
                self,
                "Guarded Hold",
                "Keine weiteren Befehle ausführen und Wärmepumpe/LTE-Modem nicht stromlos machen.",
            )
        label = record.get("event")
        hook = record.get("hook")
        if isinstance(hook, dict) and hook.get("phase"):
            label = hook["phase"]
        if label:
            self.progress_text.setText(str(label))
        info = record.get("ota_info")
        if (
            isinstance(info, dict)
            and isinstance(info.get("offset"), int)
            and isinstance(info.get("length"), int)
            and info["length"] > 0
        ):
            self.progress.setValue(min(100, round(info["offset"] * 100 / info["length"])))

    def _done(self, op, code, output):
        self.busy = False
        self._buttons()
        self._log(f"[Exit {code}]")

        if op == "ota-reattach":
            status = None
            json_start = output.find("{")
            if json_start >= 0:
                try:
                    candidate = json.loads(output[json_start:])
                    status = candidate if isinstance(candidate, dict) else None
                except json.JSONDecodeError:
                    pass
            if code == 0 and isinstance(status, dict):
                self.ota_monitoring_lost = False
                self.ota_reattach_btn.setVisible(False)
                if hasattr(self, "_handle_record"):
                    self._handle_record(status)
                hook = status.get("hook") if isinstance(status.get("hook"), dict) else {}
                phase = hook.get("phase")
                info = status.get("ota_info") if isinstance(status.get("ota_info"), dict) else {}
                if phase == "success" and hook.get("terminal") is True:
                    self.progress_text.setText("Firmwareupdate erfolgreich abgeschlossen.")
                elif phase in {"success-report"} or (
                    info.get("crc_ok") is True and info.get("length", 0) > 0
                    and info.get("offset") == info.get("length")
                ):
                    self.progress_text.setText(
                        "Firmwareübertragung abgeschlossen – Mainboard verarbeitet das Update weiter."
                    )
                elif status.get("transfer_started") is True or phase == "c5a8":
                    self.progress_text.setText("Firmwareupdate läuft weiter.")
                else:
                    self.progress_text.setText(
                        "OTA-Zustand konnte nicht sicher bestimmt werden. Keine automatische Aktion ausgeführt."
                    )
            else:
                self.ota_monitoring_lost = True
                self.ota_reattach_btn.setVisible(True)
                self.progress_text.setText(
                    "OTA-Zustand konnte nicht sicher bestimmt werden. Keine automatische Aktion ausgeführt."
                )
            self._buttons()
        elif op == "adb":
            device = next((line for line in output.splitlines() if "\tdevice" in line or " device " in line), "")
            offline = next((line for line in output.splitlines() if "\toffline" in line or " offline " in line), "")
            source = (
                f"Remote {self.remote_host.text().strip()}:{self.remote_port.value()}"
                if self.adb_remote.isChecked()
                else "Lokal"
            )
            if device:
                self.adb_state.setText(
                    f'<span style="color:#16803a;"><b>ADB verbunden ({source}):</b><br>'
                    f'<code>{device}</code></span>'
                )
                self.pending_after_reconnect = False
            elif offline and not self.pending_after_reconnect:
                self.pending_after_reconnect = True
                self.adb_state.setText(
                    f'<span style="color:#b26a00;">ADB-Gerät über {source} ist offline – '
                    'reconnect wird versucht…</span>'
                )
                self._reconnect(auto=True)
            else:
                message = (
                    f"Kein ADB-Gerät über {source} im Status device erkannt."
                    if not offline
                    else f"ADB-Gerät über {source} bleibt offline."
                )
                self.adb_state.setText(f'<span style="color:#b42318;">{message}</span>')
        elif op == "reconnect":
            if code == 0:
                adb = self._adb_path()
                if adb:
                    self._run("adb", [str(adb), "devices", "-l"])
        elif op == "status":
            try:
                data = json.loads(output)
                checks = data.get("checks", {})
                lines = [
                    (
                        f'<span style="color:#16803a;">✓ {name}</span>'
                        if ok
                        else f'<span style="color:#b42318;">✗ {name}</span>'
                    )
                    for name, ok in checks.items()
                ]
                headline = (
                    '<span style="color:#16803a;"><b>OK</b></span><br>'
                    if data.get("original_ok")
                    else '<span style="color:#b42318;"><b>NICHT OK</b></span><br>'
                )
                self.status_text.setText(headline + "<br>".join(lines))
            except Exception:
                self.status_text.setText("Status beendet – Details im Log.")
        elif op == "manifest-preview-full":
            self.manifest_preview.setPlainText(output)
            if code != 0:
                QMessageBox.critical(
                    self,
                    "Manifest-Vorschau",
                    "Automatische Firmwareanalyse fehlgeschlagen. Details stehen in der Vorschau und im Protokoll.",
                )
        elif op == "manifest-full":
            if code == 0 and self.pending_manifest_output:
                try:
                    self.manifest_preview.setPlainText(self.pending_manifest_output.read_text(encoding="utf-8"))
                except OSError:
                    pass
            QMessageBox.information(
                self,
                "Manifest",
                "Manifest automatisch erzeugt." if code == 0 else "Automatische Manifest-Erzeugung fehlgeschlagen.",
            )
        elif op == "manifest":
            if code == 0 and self.pending_manifest_output:
                try:
                    self.manifest_preview.setPlainText(self.pending_manifest_output.read_text(encoding="utf-8"))
                except OSError:
                    pass
            QMessageBox.information(
                self,
                "Manifest",
                "Manifest manuell erzeugt." if code == 0 else "Manifest-Erzeugung fehlgeschlagen.",
            )
        elif op == "backup":
            QMessageBox.information(
                self,
                "Backup",
                "Backup abgeschlossen." if code == 0 else "Backup fehlgeschlagen – Details im Log.",
            )
        elif op in ("dry", "update", "restore", "same"):
            text = {"dry": "Dry-Run", "update": "Firmwareupdate", "restore": "Restore", "same": "Gleichversionstest"}[op]
            (QMessageBox.information if code == 0 else QMessageBox.critical)(
                self, text, f"{text}: Exit-Code {code}"
            )

    def _check_adb(self):
        adb = self._require_adb()
        if adb:
            self.pending_after_reconnect = False
            self._run("adb", [str(adb), "devices", "-l"])

    def _reconnect(self, auto=False):
        adb = self._require_adb()
        if adb:
            self._run("reconnect", [str(adb), "reconnect"])

    def _reattach_ota(self):
        """Reconnect ADB and read the existing OTA session without changing it."""
        adb = self._require_adb()
        if not adb:
            return
        command = [
            str(backend_python()), str(self.controller), "--adb", str(adb),
            "--output", "json", "--no-color", "status",
        ]
        self._run_sequence(
            "ota-reattach",
            [[str(adb), "reconnect"], command],
            str(backend_dir()),
        )

    def _backup_run(self):
        adb = self._require_adb()
        if not adb:
            return
        target = Path(self.backup_path.text().strip())
        target.mkdir(parents=True, exist_ok=True)
        items = []
        if self.backup_fw.isChecked():
            items.append(("/cache/phnixIot_device_OTA", "phnixIot_device_OTA"))
        if self.backup_info.isChecked():
            items.append(("/data/phnixIot_device_OTA_INFO", "phnixIot_device_OTA_INFO"))
        if self.backup_stat.isChecked():
            items.append(("/data/phnixIot_device_statisic", "phnixIot_device_statisic"))
        if self.backup_service.isChecked():
            items.append(("/data/phnixIot4G", "phnixIot4G"))
        if not items:
            return

        commands = [
            [str(adb), "pull", remote, str(target / name)]
            for remote, name in items
        ]
        self._run_sequence("backup", commands)

    def _status_run(self):
        self._backend("status", ["run", "--check", "status"])

    def _dry(self):
        manifest = Path(self.update_manifest.text().strip())
        if manifest.is_file():
            self.progress.setValue(0)
            self._backend("dry", ["run", "--manifest", str(manifest)])

    def _update_run(self):
        manifest = Path(self.update_manifest.text().strip())
        if not manifest.is_file() or not self.risk.isChecked():
            return
        if (
            QMessageBox.warning(
                self,
                "Experimentelles Update",
                "Echter Versionswechsel noch nicht live validiert.\n\nFortfahren?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        self.progress.setValue(0)
        self._backend(
            "update",
            [
                "run", "--manifest", str(manifest), "--execute", "--confirm",
                "PHNIX-FULL-UPDATE", "--state-dir", str(self.state_dir),
            ],
        )

    def _restore(self):
        if (
            QMessageBox.question(
                self,
                "Restore",
                "Restore jetzt beim bestehenden Controller anfordern?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        ):
            self._backend("restore", ["run", "--restore", "original"])

    def _same(self):
        manifest = Path(self.same_manifest.text().strip())
        if not manifest.is_file() or not self.logger.isChecked():
            return
        self._backend(
            "same",
            [
                "same-version-test", "--manifest", str(manifest), "--execute", "--confirm",
                "PHNIX-C350-SAME-V33", "--logger-confirm", "PASSIVE-LOGGER-RUNNING",
                "--state-dir", str(self.state_dir),
            ],
        )

    def _manifest_preview_full(self):
        command = self._manifest_command(full=True, show=True)
        if command:
            self.manifest_preview.clear()
            self._run("manifest-preview-full", command, str(backend_dir()))

    def _manifest_full(self):
        firmware = Path(self.firmware.text().strip())
        if not firmware.is_file():
            QMessageBox.warning(self, "Firmware fehlt", "Bitte zuerst eine Firmwaredatei auswählen.")
            return
        output = firmware.with_suffix(".json")
        self.pending_manifest_output = output
        command = self._manifest_command(full=True, show=False, output=output)
        if command:
            self._run("manifest-full", command, str(backend_dir()))

    def _manifest_run(self):
        firmware = Path(self.firmware.text().strip())
        if not firmware.is_file() or not all(
            (self.sw_code.text().strip(), self.display_ver.text().strip(), self.ssid.text().strip())
        ):
            QMessageBox.warning(
                self,
                "Manifest",
                "Für die manuelle Fallback-Erzeugung werden Firmware, Software Code, Display-Version und Target SSID benötigt.",
            )
            return
        output = firmware.with_suffix(".json")
        self.pending_manifest_output = output
        self._run(
            "manifest",
            [
                str(backend_python()), str(self.manifest_tool), "--firmware", str(firmware),
                "--software-code", self.sw_code.text().strip(), "--display-version",
                self.display_ver.text().strip(), "--target-ssid", self.ssid.text().strip(),
                "--output", str(output),
            ],
            str(backend_dir()),
        )

    def _manifest_summary(self):
        path = Path(self.update_manifest.text().strip())
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            firmware = path.parent / str(data.get("firmware_file", ""))
            self.summary.setText(
                f"Version: <b>{data.get('display_version', '?')}</b> | Wire: {data.get('wire_version', '?')} | "
                f"Software Code: {data.get('software_code', '?')} | SSID: {data.get('target_ssid', '?')}<br>"
                f"Firmware: {data.get('firmware_file', '?')} ({'vorhanden' if firmware.is_file() else 'FEHLT'})"
            )
        except Exception:
            self.summary.setText("Noch kein gültiges Manifest ausgewählt.")
        self._buttons()

    def _buttons(self):
        adb_ready = self._adb_ready() if hasattr(self, "adb_remote") else False
        update_manifest_ready = (
            Path(self.update_manifest.text().strip()).is_file() if hasattr(self, "update_manifest") else False
        )
        firmware_ready = (
            Path(self.firmware.text().strip()).is_file() if hasattr(self, "firmware") else False
        )
        if not hasattr(self, "adb_check"):
            return
        enabled = not self.busy
        self.adb_check.setEnabled(enabled and adb_ready)
        self.adb_reconnect.setEnabled(enabled and adb_ready)
        if hasattr(self, "ota_reattach_btn"):
            self.ota_reattach_btn.setEnabled(enabled and adb_ready and self.ota_monitoring_lost)
        self.backup_button.setEnabled(enabled and adb_ready)
        self.status_btn.setEnabled(enabled and adb_ready)
        self.restore_btn.setEnabled(enabled and adb_ready)
        self.dry.setEnabled(enabled and adb_ready and update_manifest_ready)
        self.update_btn.setEnabled(enabled and adb_ready and update_manifest_ready and self.risk.isChecked())
        self.manifest_preview_btn.setEnabled(enabled and firmware_ready)
        self.manifest_full_btn.setEnabled(enabled and firmware_ready)
        self.manifest_btn.setEnabled(enabled and firmware_ready)
        if hasattr(self, "same_btn"):
            self.same_btn.setEnabled(enabled and adb_ready)

    def _log(self, text):
        self.log.appendPlainText(text)

    def _clear_log(self):
        self.log.clear()

    def _save_log(self):
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Log speichern",
            str(data_dir() / "foxair-updater.log"),
            "Log (*.log);;Text (*.txt)",
        )
        if file_name:
            Path(file_name).write_text(self.log.toPlainText() + "\n", encoding="utf-8")

    def closeEvent(self, event):
        if self.busy:
            QMessageBox.warning(
                self,
                "Vorgang läuft",
                "Während eines laufenden Vorgangs kann die Anwendung nicht geschlossen werden.",
            )
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("FoxAir Updater")
    app.setOrganizationName("FoxAir")
    icon = root_dir() / "app_icon.ico"
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
