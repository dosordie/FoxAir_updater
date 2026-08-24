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
    QApplication, QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

APP_VERSION = "0.1.0"
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

        self.setWindowTitle(f"FoxAir Updater {APP_VERSION} – EXPERIMENTELL")
        self.resize(900, 700)
        self._ui()
        self._load()
        self._buttons()

    def _ui(self):
        c = QWidget()
        v = QVBoxLayout(c)
        warning = QLabel(
            "<b>EXPERIMENTELL – echter Versionswechsel noch nicht live validiert.</b><br>"
            "Bisher wurde real nur V3.3 → V3.3 getestet; das Mainboard hat die gleiche "
            "Version erwartungsgemäß abgelehnt. Nutzung auf eigenes Risiko."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("QLabel{background:#fff1e8;border:2px solid #c84b00;padding:9px}")
        v.addWidget(warning)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._connection(), "Verbindung")
        self.tabs.addTab(self._backup(), "Backup")
        self.tabs.addTab(self._update(), "Firmware Update")
        self.tabs.addTab(self._status(), "Status / Recovery")
        self.tabs.addTab(self._manifest(), "Manifest")
        self.tabs.addTab(self._advanced(), "Erweitert")
        v.addWidget(self.tabs)

        row = QHBoxLayout()
        row.addWidget(QLabel("<b>Protokoll</b>"))
        row.addStretch()
        b = QPushButton("Log speichern…")
        b.clicked.connect(self._save_log)
        row.addWidget(b)
        v.addLayout(row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        v.addWidget(self.log, 1)
        self.setCentralWidget(c)

    def _connection(self):
        w = QWidget(); v = QVBoxLayout(w)
        row = QHBoxLayout()
        self.adb = QLineEdit(); self.adb.setPlaceholderText(r"C:\platform-tools\adb.exe")
        self.adb.editingFinished.connect(self._adb_changed)
        b = QPushButton("adb.exe auswählen…"); b.clicked.connect(self._browse_adb)
        row.addWidget(self.adb, 1); row.addWidget(b); v.addLayout(row)
        row = QHBoxLayout()
        b = QPushButton("Offizielle Platform Tools herunterladen")
        b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ADB_URL)))
        row.addWidget(b)
        b = QPushButton("LTE-/USB-Anleitung")
        b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(HOWTO_URL)))
        row.addWidget(b); row.addStretch(); v.addLayout(row)
        self.adb_state = QLabel("ADB noch nicht geprüft."); self.adb_state.setWordWrap(True); v.addWidget(self.adb_state)
        row = QHBoxLayout()
        self.adb_check = QPushButton("ADB prüfen"); self.adb_check.clicked.connect(self._check_adb)
        self.adb_reconnect = QPushButton("ADB reconnect"); self.adb_reconnect.clicked.connect(self._reconnect)
        row.addWidget(self.adb_check); row.addWidget(self.adb_reconnect); row.addStretch(); v.addLayout(row)
        n = QLabel("ADB wird nicht mitgeliefert. Der Download-Button öffnet nur die offizielle Google-Seite.")
        n.setWordWrap(True); v.addWidget(n); v.addStretch()
        return w

    def _backup(self):
        w = QWidget(); v = QVBoxLayout(w)
        row = QHBoxLayout()
        self.backup_path = QLineEdit()
        b = QPushButton("Zielordner…"); b.clicked.connect(self._browse_backup)
        row.addWidget(self.backup_path, 1); row.addWidget(b); v.addLayout(row)
        self.backup_fw = QCheckBox("Firmware"); self.backup_fw.setChecked(True)
        self.backup_info = QCheckBox("OTA_INFO"); self.backup_info.setChecked(True)
        self.backup_stat = QCheckBox("Statistik"); self.backup_stat.setChecked(True)
        self.backup_service = QCheckBox("Originaldienst phnixIot4G")
        for x in (self.backup_fw, self.backup_info, self.backup_stat, self.backup_service): v.addWidget(x)
        self.backup_button = QPushButton("Backup erstellen"); self.backup_button.clicked.connect(self._backup_run); v.addWidget(self.backup_button)
        n = QLabel("Read-only: Die Funktion verwendet ausschließlich adb pull und verändert nichts am LTE-Modem.")
        n.setWordWrap(True); v.addWidget(n); v.addStretch()
        return w

    def _update(self):
        w = QWidget(); v = QVBoxLayout(w)
        row = QHBoxLayout()
        self.update_manifest = QLineEdit(); self.update_manifest.textChanged.connect(self._manifest_summary)
        b = QPushButton("Manifest…"); b.clicked.connect(lambda: self._pick_manifest(self.update_manifest))
        row.addWidget(self.update_manifest, 1); row.addWidget(b); v.addLayout(row)
        self.summary = QLabel("Noch kein Manifest ausgewählt."); self.summary.setWordWrap(True); v.addWidget(self.summary)
        self.progress_text = QLabel("Kein Update aktiv."); v.addWidget(self.progress_text)
        self.progress = QProgressBar(); v.addWidget(self.progress)
        self.dry = QPushButton("Vorprüfung / Dry-Run"); self.dry.clicked.connect(self._dry); v.addWidget(self.dry)
        self.risk = QCheckBox("Risiko eines noch nicht live validierten Versionswechsels verstanden.")
        self.risk.toggled.connect(self._buttons); v.addWidget(self.risk)
        self.update_btn = QPushButton("FIRMWAREUPDATE STARTEN"); self.update_btn.clicked.connect(self._update_run); v.addWidget(self.update_btn)
        v.addStretch(); return w

    def _status(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.status_btn = QPushButton("Originalzustand prüfen"); self.status_btn.clicked.connect(self._status_run); v.addWidget(self.status_btn)
        self.status_text = QLabel("Noch kein Statuscheck."); self.status_text.setWordWrap(True); v.addWidget(self.status_text)
        n = QLabel("Restore ist nur vor begonnenem C5A8 zulässig. Die Entscheidung trifft ausschließlich der bestehende Controller.")
        n.setWordWrap(True); v.addWidget(n)
        self.restore_btn = QPushButton("Originalzustand wiederherstellen"); self.restore_btn.clicked.connect(self._restore); v.addWidget(self.restore_btn)
        v.addStretch(); return w

    def _manifest(self):
        w = QWidget(); form = QFormLayout(w)
        row = QWidget(); h = QHBoxLayout(row); h.setContentsMargins(0,0,0,0)
        self.firmware = QLineEdit(); b = QPushButton("Firmware…"); b.clicked.connect(self._pick_firmware)
        h.addWidget(self.firmware,1); h.addWidget(b); form.addRow("Firmware:", row)
        self.sw_code = QLineEdit(); self.sw_code.setPlaceholderText("82400644"); form.addRow("Software Code:", self.sw_code)
        self.display_ver = QLineEdit(); self.display_ver.setPlaceholderText("V3.4"); form.addRow("Display-Version:", self.display_ver)
        self.ssid = QLineEdit(); self.ssid.setPlaceholderText("0063"); form.addRow("Target SSID:", self.ssid)
        self.manifest_btn = QPushButton("Manifest erzeugen"); self.manifest_btn.clicked.connect(self._manifest_run); form.addRow("", self.manifest_btn)
        return w

    def _advanced(self):
        w = QWidget(); v = QVBoxLayout(w)
        row = QHBoxLayout()
        self.same_manifest = QLineEdit(); self.same_manifest.textChanged.connect(self._buttons)
        b = QPushButton("Manifest…"); b.clicked.connect(lambda: self._pick_manifest(self.same_manifest))
        row.addWidget(self.same_manifest,1); row.addWidget(b); v.addLayout(row)
        self.logger = QCheckBox("Passiver RS485-Logger läuft tatsächlich"); self.logger.toggled.connect(self._buttons); v.addWidget(self.logger)
        self.same_btn = QPushButton("Gleichversionstest starten"); self.same_btn.clicked.connect(self._same); v.addWidget(self.same_btn)
        v.addStretch(); return w

    def _load(self):
        saved = str(self.settings.value("adb", "") or "")
        found = Path(saved) if saved and Path(saved).is_file() else self._find_adb()
        if found: self.adb.setText(str(found))
        self.backup_path.setText(str(self.settings.value("backup", Path.home() / "FoxAir_LTE_Backup")))

    def _find_adb(self):
        candidates = []
        if shutil.which("adb"): candidates.append(Path(shutil.which("adb")))
        if os.environ.get("LOCALAPPDATA"):
            candidates.append(Path(os.environ["LOCALAPPDATA"]) / "Android/Sdk/platform-tools/adb.exe")
        candidates += [Path.home() / "platform-tools/adb.exe", Path(r"C:\platform-tools\adb.exe")]
        return next((p for p in candidates if p.is_file()), None)

    def _adb_path(self):
        p = Path(self.adb.text().strip().strip('"')) if self.adb.text().strip() else None
        return p if p and p.is_file() else None

    def _adb_changed(self):
        self.settings.setValue("adb", self.adb.text().strip().strip('"')); self._buttons()

    def _browse_adb(self):
        f, _ = QFileDialog.getOpenFileName(self, "adb.exe auswählen", str(Path.home()), "ADB (adb.exe)")
        if f: self.adb.setText(f); self._adb_changed()

    def _browse_backup(self):
        d = QFileDialog.getExistingDirectory(self, "Backup-Ziel", self.backup_path.text())
        if d: self.backup_path.setText(d); self.settings.setValue("backup", d)

    def _pick_manifest(self, field):
        f, _ = QFileDialog.getOpenFileName(self, "Manifest auswählen", str(Path.home()), "Manifest (*.json)")
        if f: field.setText(f)

    def _pick_firmware(self):
        f, _ = QFileDialog.getOpenFileName(self, "Firmware auswählen", str(Path.home()), "Firmware (*.bin);;Alle Dateien (*)")
        if f: self.firmware.setText(f)

    def _require_adb(self):
        p = self._adb_path()
        if not p:
            QMessageBox.warning(self, "ADB fehlt", "Bitte zuerst adb.exe auswählen oder über den offiziellen Link herunterladen.")
            self.tabs.setCurrentIndex(0)
        return p

    def _run(self, op, command, cwd=None):
        if self.busy: return
        self.busy = True; self._buttons(); self._log("$ " + subprocess.list2cmdline([str(x) for x in command]))
        def work():
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            env = os.environ.copy(); env["PYTHONUTF8"]="1"; env["PYTHONUNBUFFERED"]="1"
            out = []
            try:
                p = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace", creationflags=flags, env=env)
                for line in p.stdout or []:
                    line=line.rstrip("\r\n"); out.append(line); self.signals.line.emit(line)
                self.signals.done.emit(op, p.wait(), "\n".join(out))
            except Exception as e:
                self.signals.line.emit("[Prozessfehler] " + str(e)); self.signals.done.emit(op, -1, str(e))
        threading.Thread(target=work, daemon=True).start()

    def _backend(self, op, args):
        adb = self._require_adb()
        if not adb: return
        cmd = [str(backend_python()), str(self.controller), "--adb", str(adb), "--output", "json", "--no-color", *args]
        self._run(op, cmd, str(backend_dir()))

    def _line(self, text):
        self._log(text)
        try:
            rec = json.loads(text)
        except Exception:
            return
        if not isinstance(rec, dict): return
        event = rec.get("event")
        if event in ("guarded-hold", "manual-recovery-required"):
            QMessageBox.critical(self, "Guarded Hold", "Keine weiteren Befehle ausführen und Wärmepumpe/LTE-Modem nicht stromlos machen.")
        label = rec.get("event")
        hook = rec.get("hook")
        if isinstance(hook, dict) and hook.get("phase"): label = hook["phase"]
        if label: self.progress_text.setText(str(label))
        info = rec.get("ota_info")
        if isinstance(info, dict) and isinstance(info.get("offset"), int) and isinstance(info.get("length"), int) and info["length"] > 0:
            self.progress.setValue(min(100, round(info["offset"] * 100 / info["length"])))

    def _done(self, op, code, output):
        self.busy = False; self._buttons(); self._log(f"[Exit {code}]")
        if op == "adb":
            device = next((x for x in output.splitlines() if "\tdevice" in x or " device " in x), "")
            offline = next((x for x in output.splitlines() if "\toffline" in x or " offline " in x), "")
            if device:
                self.adb_state.setText("<b>ADB verbunden:</b><br><code>"+device+"</code>"); self.pending_after_reconnect=False
            elif offline and not self.pending_after_reconnect:
                self.pending_after_reconnect=True; self.adb_state.setText("ADB offline – reconnect wird versucht…"); self._reconnect(auto=True)
            else:
                self.adb_state.setText("Kein ADB-Gerät im Status device erkannt." if not offline else "ADB-Gerät bleibt offline.")
        elif op == "reconnect":
            if code == 0:
                adb=self._adb_path()
                if adb: self._run("adb",[str(adb),"devices","-l"])
        elif op == "status":
            try:
                d=json.loads(output); checks=d.get("checks",{})
                lines=[("✓ " if ok else "✗ ")+name for name,ok in checks.items()]
                self.status_text.setText(("<b>OK</b><br>" if d.get("original_ok") else "<b>NICHT OK</b><br>")+"<br>".join(lines))
            except Exception: self.status_text.setText("Status beendet – Details im Log.")
        elif op == "manifest":
            QMessageBox.information(self, "Manifest", "Manifest erzeugt." if code==0 else "Manifest-Erzeugung fehlgeschlagen.")
        elif op == "backup":
            QMessageBox.information(self, "Backup", "Backup abgeschlossen." if code==0 else "Backup fehlgeschlagen – Details im Log.")
        elif op in ("dry","update","restore","same"):
            text={"dry":"Dry-Run","update":"Firmwareupdate","restore":"Restore","same":"Gleichversionstest"}[op]
            (QMessageBox.information if code==0 else QMessageBox.critical)(self, text, f"{text}: Exit-Code {code}")

    def _check_adb(self):
        adb=self._require_adb()
        if adb: self.pending_after_reconnect=False; self._run("adb",[str(adb),"devices","-l"])

    def _reconnect(self, auto=False):
        adb=self._require_adb()
        if adb: self._run("reconnect",[str(adb),"reconnect"])

    def _backup_run(self):
        adb=self._require_adb()
        if not adb: return
        target=Path(self.backup_path.text().strip()); target.mkdir(parents=True,exist_ok=True)
        items=[]
        if self.backup_fw.isChecked(): items.append(("/cache/phnixIot_device_OTA","phnixIot_device_OTA"))
        if self.backup_info.isChecked(): items.append(("/data/phnixIot_device_OTA_INFO","phnixIot_device_OTA_INFO"))
        if self.backup_stat.isChecked(): items.append(("/data/phnixIot_device_statisic","phnixIot_device_statisic"))
        if self.backup_service.isChecked(): items.append(("/data/phnixIot4G","phnixIot4G"))
        if not items: return
        cmd = " && ".join(f'"{adb}" pull "{remote}" "{target/name}"' for remote,name in items)
        self._run("backup", ["cmd.exe","/d","/s","/c",cmd])

    def _status_run(self): self._backend("status",["run","--check","status"])
    def _dry(self):
        p=Path(self.update_manifest.text().strip())
        if p.is_file(): self.progress.setValue(0); self._backend("dry",["run","--manifest",str(p)])

    def _update_run(self):
        p=Path(self.update_manifest.text().strip())
        if not p.is_file() or not self.risk.isChecked(): return
        if QMessageBox.warning(self,"Experimentelles Update","Echter Versionswechsel noch nicht live validiert.\n\nFortfahren?",
                               QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes: return
        self.progress.setValue(0)
        self._backend("update",["run","--manifest",str(p),"--execute","--confirm","PHNIX-FULL-UPDATE","--state-dir",str(self.state_dir)])

    def _restore(self):
        if QMessageBox.question(self,"Restore","Restore jetzt beim bestehenden Controller anfordern?",
                                QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
            self._backend("restore",["run","--restore","original"])

    def _same(self):
        p=Path(self.same_manifest.text().strip())
        if not p.is_file() or not self.logger.isChecked(): return
        self._backend("same",["same-version-test","--manifest",str(p),"--execute","--confirm","PHNIX-C350-SAME-V33",
                              "--logger-confirm","PASSIVE-LOGGER-RUNNING","--state-dir",str(self.state_dir)])

    def _manifest_run(self):
        fw=Path(self.firmware.text().strip())
        if not fw.is_file() or not all((self.sw_code.text().strip(),self.display_ver.text().strip(),self.ssid.text().strip())): return
        out=fw.with_suffix(".json")
        self._run("manifest",[str(backend_python()),str(self.manifest_tool),"--firmware",str(fw),"--software-code",self.sw_code.text().strip(),
                              "--display-version",self.display_ver.text().strip(),"--target-ssid",self.ssid.text().strip(),"--output",str(out)],str(backend_dir()))

    def _manifest_summary(self):
        p=Path(self.update_manifest.text().strip())
        try:
            d=json.loads(p.read_text(encoding="utf-8")); fw=p.parent/str(d.get("firmware_file",""))
            self.summary.setText(f"Version: <b>{d.get('display_version','?')}</b> | Wire: {d.get('wire_version','?')} | "
                                 f"Software Code: {d.get('software_code','?')} | SSID: {d.get('target_ssid','?')}<br>"
                                 f"Firmware: {d.get('firmware_file','?')} ({'vorhanden' if fw.is_file() else 'FEHLT'})")
        except Exception: self.summary.setText("Noch kein gültiges Manifest ausgewählt.")
        self._buttons()

    def _buttons(self):
        adb=self._adb_path() is not None; m=Path(self.update_manifest.text().strip()).is_file() if hasattr(self,"update_manifest") else False
        sm=Path(self.same_manifest.text().strip()).is_file() if hasattr(self,"same_manifest") else False
        if not hasattr(self,"adb_check"): return
        enabled=not self.busy
        self.adb_check.setEnabled(enabled and adb); self.adb_reconnect.setEnabled(enabled and adb)
        self.backup_button.setEnabled(enabled and adb); self.status_btn.setEnabled(enabled and adb); self.restore_btn.setEnabled(enabled and adb)
        self.dry.setEnabled(enabled and adb and m); self.update_btn.setEnabled(enabled and adb and m and self.risk.isChecked())
        self.manifest_btn.setEnabled(enabled); self.same_btn.setEnabled(enabled and adb and sm and self.logger.isChecked())

    def _log(self,text): self.log.appendPlainText(text)

    def _save_log(self):
        f,_=QFileDialog.getSaveFileName(self,"Log speichern",str(data_dir()/"foxair-updater.log"),"Log (*.log);;Text (*.txt)")
        if f: Path(f).write_text(self.log.toPlainText()+"\n",encoding="utf-8")

    def closeEvent(self,event):
        if self.busy:
            QMessageBox.warning(self,"Vorgang läuft","Während eines laufenden Vorgangs kann die Anwendung nicht geschlossen werden."); event.ignore()
        else: event.accept()


def main():
    app=QApplication(sys.argv); app.setApplicationName("FoxAir Updater"); app.setOrganizationName("FoxAir")
    w=MainWindow(); w.show(); return app.exec()


if __name__=="__main__":
    raise SystemExit(main())
