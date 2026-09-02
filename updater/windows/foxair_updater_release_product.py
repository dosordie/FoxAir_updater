from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton

import foxair_updater_gui as base
import foxair_updater_runner_product as product


class MainWindow(product.MainWindow):
    """Release entrypoint with one-click support diagnostics."""

    def _ui(self):
        super()._ui()
        clear_button = next(
            (
                button
                for button in self.findChildren(QPushButton)
                if button.text() == "Protokoll leeren"
            ),
            None,
        )
        root_layout = self.centralWidget().layout() if self.centralWidget() else None
        toolbar = self._layout_containing(root_layout, clear_button)
        if toolbar is None or clear_button is None:
            return
        self.diagnostics_button = QPushButton("Diagnosepaket speichern…")
        self.diagnostics_button.setToolTip(
            "Speichert den sichtbaren GUI-Log sowie die Textdiagnose des letzten/aktiven "
            "DTU-OTA-Laufs als ZIP. Firmware, OTA_INFO und Statistik-Binärdaten werden nicht eingebunden."
        )
        self.diagnostics_button.clicked.connect(self._save_diagnostic_bundle)
        toolbar.insertWidget(max(0, toolbar.indexOf(clear_button)), self.diagnostics_button)

    @staticmethod
    def _diagnostics_core_path() -> Path:
        return base.backend_dir() / "updater/dtu_ota/diagnostics.py"

    def _save_diagnostic_bundle(self) -> None:
        if self.busy:
            return
        adb = self._require_adb()
        if not adb:
            return
        core = self._diagnostics_core_path()
        if not core.is_file():
            QMessageBox.critical(
                self,
                "Diagnosefunktion fehlt",
                f"Der Diagnose-Core wurde nicht gefunden:\n{core}",
            )
            return

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        default = base.data_dir() / f"FoxAir_Diagnose_{stamp}.zip"
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Diagnosepaket speichern",
            str(default),
            "ZIP (*.zip)",
        )
        if not file_name:
            return
        output = Path(file_name)
        if output.suffix.lower() != ".zip":
            output = output.with_suffix(".zip")

        host_log = base.data_dir() / "diagnostics-current-gui.log"
        try:
            host_log.write_text(self.log.toPlainText(), encoding="utf-8")
        except OSError as error:
            QMessageBox.critical(self, "Diagnosepaket", f"GUI-Protokoll konnte nicht vorbereitet werden:\n{error}")
            return

        self._diagnostic_output = output
        self._diagnostic_host_log = host_log
        command = [
            str(base.backend_python()),
            str(core),
            "--adb",
            str(adb),
            "--output",
            str(output),
            "--host-log",
            str(host_log),
            "--app-version",
            base.APP_VERSION,
        ]
        run_id = getattr(self, "_runner_run_id", None)
        if isinstance(run_id, str) and run_id.strip():
            command += ["--run-id", run_id.strip()]
        self._run("runner-diagnostics", command, str(base.backend_dir()))

    def _done(self, op, code, output):
        if op != "runner-diagnostics":
            super()._done(op, code, output)
            return

        super()._done("handled-result", code, output)
        host_log = getattr(self, "_diagnostic_host_log", None)
        if isinstance(host_log, Path):
            try:
                host_log.unlink(missing_ok=True)
            except OSError:
                pass

        parsed = None
        for line in reversed(output.splitlines()):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "ok" in value:
                parsed = value
                break

        if code == 0 and parsed and parsed.get("ok") is True:
            missing = parsed.get("missing") or {}
            suffix = ""
            if isinstance(missing, dict) and missing:
                suffix = "\n\nEinige optionale Dateien waren nicht vorhanden; dies ist bei manchen Laufphasen normal."
            QMessageBox.information(
                self,
                "Diagnosepaket gespeichert",
                f"Das Diagnosepaket wurde gespeichert:\n{parsed.get('output', self._diagnostic_output)}"
                "\n\nFirmware, OTA_INFO und Statistik-Binärdaten wurden nicht eingebunden. "
                "Bekannte Geräte-/Cloudkennungen werden in Textdateien maskiert."
                + suffix,
            )
            return

        detail = parsed.get("error") if isinstance(parsed, dict) else "Unbekannter Fehler"
        QMessageBox.critical(
            self,
            "Diagnosepaket fehlgeschlagen",
            f"Das Diagnosepaket konnte nicht erstellt werden.\n\n{detail}\n\nDetails stehen im Protokoll.",
        )


def main() -> int:
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
