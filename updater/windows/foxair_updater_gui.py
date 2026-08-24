from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QStandardPaths, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

APP_VERSION = "0.1.1"
ADB_URL = "https://developer.android.com/tools/releases/platform-tools?hl=de#downloads"
HOWTO_URL = "https://github.com/dosordie/FoxAir_updater/blob/main/docs/HowTo/firmware_backup_lte.md"


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
        self.controller = backend_dir() / "tools/phnix_ota/phnix_local_ota_controller.py"
        self.manifest_tool = backend_dir() / "tools/phnix_ota/create_firmware_manifest.py"
        self.state_dir = data_dir() / "phnix-ota-state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.pending_manifest_output: Path | None = None

        self.setWindowTitle(f"FoxAir Updater {APP_VERSION} – EXPERIMENTELL")
        self.resize(930, 740)
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
        self.tabs.addTab(self._status(), "Status / Recovery")
        self.tabs.addTab(self._manifest(), "Manifest")
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
        self.adb = QLineEdit()
        self.adb.setPlaceholderText(r"C:\platform-tools\adb.exe")
        self.adb.editingFinished.connect(self._adb_changed)
        button = QPushButton("adb.exe auswählen…")
        button.clicked.connect(self._browse_adb)
        row.addWidget(self.adb, 1)
        row.addWidget(button)
        layout.addLayout(row)

        row = QHBoxLayout()
        button = QPushButton("Offizielle Platform Tools herunterladen")
        button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ADB_URL)))
        row.addWidget(button)
        button = QPushButton("LTE-/USB-Anleitung")
        button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(HOWTO_URL)))
        row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)

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
            "ADB wird nicht mitgeliefert. Der Download-Button öffnet nur die "
            "offizielle Google-Seite."
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
        row.addWidget(self.backup_path, 1)
        row.addWidget(button)
        layout.addLayout(row)

        self.backup_fw = QCheckBox("Firmware")
        self.backup_fw.setChecked(True)
        self.backup_info = QCheckBox("OTA_INFO")
        self.backup_info.setChecked(True)
        self.backup_stat = QCheckBox("Statistik")
        self.backup_stat.setChecked(True)
        self.backup_service = QCheckBox("Originaldienst phnixIot4G")
        for item in (
            self.backup_fw,
            self.backup_info,
            self.backup_stat,
            self.backup_service,
        ):
            layout.addWidget(item)

        self.backup_button = QPushButton("Backup erstellen")
        self.backup_button.clicked.connect(self._backup_run)
        layout.addWidget(self.backup_button)

        note = QLabel(
            "Read-only: Die Funktion verwendet ausschließlich adb pull und verändert "
            "nichts am LTE-Modem."
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
        layout.addWidget(self.progress_text)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)

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

        self.status_text = QLabel("Noch kein Statuscheck.")
        self.status_text.setWordWrap(True)
        layout.addWidget(self.status_text)

        note = QLabel(
            "Restore ist nur vor begonnenem C5A8 zulässig. Die Entscheidung trifft "
            "ausschließlich der bestehende Controller."
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

        row = QHBoxLayout()
        self.firmware = QLineEdit()
        button = QPushButton("Firmware…")
        button.clicked.connect(self._pick_firmware)
        row.addWidget(QLabel("Firmware:"))
        row.addWidget(self.firmware, 1)
        row.addWidget(button)
        layout.addLayout(row)

        auto_note = QLabel(
            "<b>Empfohlen:</b> Die Full-Variante analysiert die Firmware selbst, "
            "liest Software-Code und Version aus dem Image und berechnet die übrigen "
            "Manifestfelder. Sie arbeitet fail-closed, wenn die Firmware-Identität "
            "nicht eindeutig erkannt wird."
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
            "<b>Fallback / manuell:</b> Nur verwenden, wenn die automatische "
            "Firmwareanalyse nicht möglich ist und die Werte sicher bekannt sind."
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

        row = QHBoxLayout()
        self.same_manifest = QLineEdit()
        self.same_manifest.textChanged.connect(self._buttons)
        button = QPushButton("Manifest…")
        button.clicked.connect(lambda: self._pick_manifest(self.same_manifest))
        row.addWidget(self.same_manifest, 1)
        row.addWidget(button)
        layout.addLayout(row)

        self.logger = QCheckBox("Passiver RS485-Logger läuft tatsächlich")
        self.logger.toggled.connect(self._buttons)
        layout.addWidget(self.logger)

        self.same_btn = QPushButton("Gleichversionstest starten")
        self.same_btn.clicked.connect(self._same)
        layout.addWidget(self.same_btn)
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

    def _find_adb(self):
        candidates = []
        found = shutil.which("adb")
        if found:
            candidates.append(Path(found))
        if os.environ.get("LOCALAPPDATA"):
            candidates.append(
                Path(os.environ["LOCALAPPDATA"])
                / "Android/Sdk/platform-tools/adb.exe"
            )
        candidates += [
            Path.home() / "platform-tools/adb.exe",
            Path(r"C:\platform-tools\adb.exe"),
        ]
        return next((path for path in candidates if path.is_file()), None)

    def _adb_path(self):
        value = self.adb.text().strip().strip('"')
        path = Path(value) if value else None
        return path if path and path.is_file() else None

    def _adb_changed(self):
        self.settings.setValue("adb", self.adb.text().strip().strip('"'))
        self._buttons()

    def _browse_adb(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "adb.exe auswählen", str(Path.home()), "ADB (adb.exe)"
        )
        if file_name:
            self.adb.setText(file_name)
            self._adb_changed()

    def _browse_backup(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Backup-Ziel", self.backup_path.text()
        )
        if directory:
            self.backup_path.setText(directory)
            self.settings.setValue("backup", directory)

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
            "Firmware (*.bin);;Alle Dateien (*)",
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
        return path

    def _run(self, op, command, cwd=None):
        if self.busy:
            return
        self.busy = True
        self._buttons()
        self._log("$ " + subprocess.list2cmdline([str(item) for item in command]))

        def work():
            flags = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            )
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            env["PYTHONUNBUFFERED"] = "1"
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
                    env=env,
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

        command = [
            str(backend_python()),
            str(self.manifest_tool),
            "--firmware",
            str(firmware),
        ]
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
                "Keine weiteren Befehle ausführen und Wärmepumpe/LTE-Modem "
                "nicht stromlos machen.",
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
            self.progress.setValue(
                min(100, round(info["offset"] * 100 / info["length"]))
            )

    def _done(self, op, code, output):
        self.busy = False
        self._buttons()
        self._log(f"[Exit {code}]")

        if op == "adb":
            device = next(
                (
                    line
                    for line in output.splitlines()
                    if "\tdevice" in line or " device " in line
                ),
                "",
            )
            offline = next(
                (
                    line
                    for line in output.splitlines()
                    if "\toffline" in line or " offline " in line
                ),
                "",
            )
            if device:
                self.adb_state.setText(
                    "<b>ADB verbunden:</b><br><code>" + device + "</code>"
                )
                self.pending_after_reconnect = False
            elif offline and not self.pending_after_reconnect:
                self.pending_after_reconnect = True
                self.adb_state.setText("ADB offline – reconnect wird versucht…")
                self._reconnect(auto=True)
            else:
                self.adb_state.setText(
                    "Kein ADB-Gerät im Status device erkannt."
                    if not offline
                    else "ADB-Gerät bleibt offline."
                )

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
                    ("✓ " if ok else "✗ ") + name for name, ok in checks.items()
                ]
                self.status_text.setText(
                    ("<b>OK</b><br>" if data.get("original_ok") else "<b>NICHT OK</b><br>")
                    + "<br>".join(lines)
                )
            except Exception:
                self.status_text.setText("Status beendet – Details im Log.")

        elif op == "manifest-preview-full":
            self.manifest_preview.setPlainText(output)
            if code != 0:
                QMessageBox.critical(
                    self,
                    "Manifest-Vorschau",
                    "Automatische Firmwareanalyse fehlgeschlagen. Details stehen in "
                    "der Vorschau und im Protokoll.",
                )

        elif op == "manifest-full":
            if code == 0 and self.pending_manifest_output:
                try:
                    self.manifest_preview.setPlainText(
                        self.pending_manifest_output.read_text(encoding="utf-8")
                    )
                except OSError:
                    pass
            QMessageBox.information(
                self,
                "Manifest",
                "Manifest automatisch erzeugt."
                if code == 0
                else "Automatische Manifest-Erzeugung fehlgeschlagen.",
            )

        elif op == "manifest":
            if code == 0 and self.pending_manifest_output:
                try:
                    self.manifest_preview.setPlainText(
                        self.pending_manifest_output.read_text(encoding="utf-8")
                    )
                except OSError:
                    pass
            QMessageBox.information(
                self,
                "Manifest",
                "Manifest manuell erzeugt."
                if code == 0
                else "Manifest-Erzeugung fehlgeschlagen.",
            )

        elif op == "backup":
            QMessageBox.information(
                self,
                "Backup",
                "Backup abgeschlossen."
                if code == 0
                else "Backup fehlgeschlagen – Details im Log.",
            )

        elif op in ("dry", "update", "restore", "same"):
            text = {
                "dry": "Dry-Run",
                "update": "Firmwareupdate",
                "restore": "Restore",
                "same": "Gleichversionstest",
            }[op]
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
            items.append(
                ("/data/phnixIot_device_OTA_INFO", "phnixIot_device_OTA_INFO")
            )
        if self.backup_stat.isChecked():
            items.append(
                ("/data/phnixIot_device_statisic", "phnixIot_device_statisic")
            )
        if self.backup_service.isChecked():
            items.append(("/data/phnixIot4G", "phnixIot4G"))
        if not items:
            return

        command_text = " && ".join(
            f'"{adb}" pull "{remote}" "{target / name}"'
            for remote, name in items
        )
        self._run("backup", ["cmd.exe", "/d", "/s", "/c", command_text])

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
                "run",
                "--manifest",
                str(manifest),
                "--execute",
                "--confirm",
                "PHNIX-FULL-UPDATE",
                "--state-dir",
                str(self.state_dir),
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
                "same-version-test",
                "--manifest",
                str(manifest),
                "--execute",
                "--confirm",
                "PHNIX-C350-SAME-V33",
                "--logger-confirm",
                "PASSIVE-LOGGER-RUNNING",
                "--state-dir",
                str(self.state_dir),
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
            QMessageBox.warning(
                self, "Firmware fehlt", "Bitte zuerst eine Firmwaredatei auswählen."
            )
            return
        output = firmware.with_suffix(".json")
        self.pending_manifest_output = output
        command = self._manifest_command(full=True, show=False, output=output)
        if command:
            self._run("manifest-full", command, str(backend_dir()))

    def _manifest_run(self):
        firmware = Path(self.firmware.text().strip())
        if not firmware.is_file() or not all(
            (
                self.sw_code.text().strip(),
                self.display_ver.text().strip(),
                self.ssid.text().strip(),
            )
        ):
            QMessageBox.warning(
                self,
                "Manifest",
                "Für die manuelle Fallback-Erzeugung werden Firmware, Software Code, "
                "Display-Version und Target SSID benötigt.",
            )
            return

        output = firmware.with_suffix(".json")
        self.pending_manifest_output = output
        self._run(
            "manifest",
            [
                str(backend_python()),
                str(self.manifest_tool),
                "--firmware",
                str(firmware),
                "--software-code",
                self.sw_code.text().strip(),
                "--display-version",
                self.display_ver.text().strip(),
                "--target-ssid",
                self.ssid.text().strip(),
                "--output",
                str(output),
            ],
            str(backend_dir()),
        )

    def _manifest_summary(self):
        path = Path(self.update_manifest.text().strip())
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            firmware = path.parent / str(data.get("firmware_file", ""))
            self.summary.setText(
                f"Version: <b>{data.get('display_version', '?')}</b> | "
                f"Wire: {data.get('wire_version', '?')} | "
                f"Software Code: {data.get('software_code', '?')} | "
                f"SSID: {data.get('target_ssid', '?')}<br>"
                f"Firmware: {data.get('firmware_file', '?')} "
                f"({'vorhanden' if firmware.is_file() else 'FEHLT'})"
            )
        except Exception:
            self.summary.setText("Noch kein gültiges Manifest ausgewählt.")
        self._buttons()

    def _buttons(self):
        adb_ready = self._adb_path() is not None
        update_manifest_ready = (
            Path(self.update_manifest.text().strip()).is_file()
            if hasattr(self, "update_manifest")
            else False
        )
        same_manifest_ready = (
            Path(self.same_manifest.text().strip()).is_file()
            if hasattr(self, "same_manifest")
            else False
        )
        firmware_ready = (
            Path(self.firmware.text().strip()).is_file()
            if hasattr(self, "firmware")
            else False
        )

        if not hasattr(self, "adb_check"):
            return

        enabled = not self.busy
        self.adb_check.setEnabled(enabled and adb_ready)
        self.adb_reconnect.setEnabled(enabled and adb_ready)
        self.backup_button.setEnabled(enabled and adb_ready)
        self.status_btn.setEnabled(enabled and adb_ready)
        self.restore_btn.setEnabled(enabled and adb_ready)
        self.dry.setEnabled(enabled and adb_ready and update_manifest_ready)
        self.update_btn.setEnabled(
            enabled
            and adb_ready
            and update_manifest_ready
            and self.risk.isChecked()
        )
        self.manifest_preview_btn.setEnabled(enabled and firmware_ready)
        self.manifest_full_btn.setEnabled(enabled and firmware_ready)
        self.manifest_btn.setEnabled(enabled and firmware_ready)
        self.same_btn.setEnabled(
            enabled
            and adb_ready
            and same_manifest_ready
            and self.logger.isChecked()
        )

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
            Path(file_name).write_text(
                self.log.toPlainText() + "\n", encoding="utf-8"
            )

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
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
