from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import foxair_updater_gui as base
import foxair_updater_maintenance as legacy


RUNNER_POLL_MS = 7000


class MainWindow(legacy.MainWindow):
    """Existing FoxAir Windows shell with autonomous DTU OTA orchestration."""

    def __init__(self):
        self._runner_run_id: str | None = None
        self._runner_prepared_manifest: Path | None = None
        self._runner_active = False
        self._runner_abort_allowed = False
        self._runner_terminal = False
        self._runner_acknowledged = False
        self._runner_autostart_after_prepare = False
        self._runner_prepare_mode = "full"
        self._runner_terminal_notified: set[str] = set()
        super().__init__()
        self._runner_timer = QTimer(self)
        self._runner_timer.setInterval(RUNNER_POLL_MS)
        self._runner_timer.timeout.connect(self._poll_runner_status)
        self.setWindowTitle(self.windowTitle() + " – DTU Runner")

    def _runner_cli(self) -> Path:
        return base.backend_dir() / "tools/dtu_ota_runner/cli.py"

    def _runner_command(self, *args: str) -> list[str] | None:
        adb = self._require_adb()
        if not adb:
            return None
        return [
            str(base.backend_python()),
            str(self._runner_cli()),
            "--adb",
            str(adb),
            *args,
        ]

    def _run_runner(self, op: str, *args: str) -> None:
        command = self._runner_command(*args)
        if command:
            self._run(op, command, str(base.backend_dir()))

    @staticmethod
    def _runner_json(output: str) -> dict | None:
        start = output.find("{")
        if start < 0:
            return None
        try:
            value = json.loads(output[start:])
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def _update(self):
        widget = super()._update()
        layout = widget.layout()
        note = QLabel(
            "<b>Autonomer DTU-Runner:</b> Windows bereitet das Paket vor und startet den Lauf. "
            "Danach entscheidet und überwacht das LTE-Modem den Mainboard-OTA selbstständig. "
            "Ein Verlust der ADB-/Windows-Verbindung beendet das Update nicht."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "QLabel{background:#f7f8fa;border:1px solid #d0d5dd;padding:9px;}"
        )
        layout.insertWidget(0, note)
        self.dry.setText("Vorprüfung / Paket auf DTU vorbereiten")
        self.update_btn.setText("AUTONOMES FIRMWAREUPDATE STARTEN")
        self.ota_reattach_btn.setText("ADB neu verbinden / Runner-Status prüfen")
        self.progress.setTextVisible(True)
        return widget

    def _status(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        note = QLabel(
            "<b>Autonomer OTA-Status:</b> Diese Seite liest ausschließlich den persistenten "
            "Runner-Zustand unter <code>/data/foxair_ota_runner</code>. Windows führt keine "
            "C350/C36E/C357/C5A8-Entscheidung aus. Ein Abbruch wird nur als Anfrage an den "
            "DTU-Runner geschrieben und ist nach dem Point-of-no-return gesperrt."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.status_text = QLabel("Noch kein Runner-Status gelesen.")
        self.status_text.setWordWrap(True)
        self.status_text.setStyleSheet(
            "QLabel{background:#f7f8fa;border:1px solid #d0d5dd;padding:9px;}"
        )
        layout.addWidget(self.status_text)

        row = QHBoxLayout()
        self.status_btn = QPushButton("Aktuellen Runner-Status lesen")
        self.status_btn.clicked.connect(self._status_run)
        row.addWidget(self.status_btn)
        self.runner_log_btn = QPushButton("Runner-Log lesen")
        self.runner_log_btn.clicked.connect(self._runner_log)
        row.addWidget(self.runner_log_btn)
        row.addStretch()
        layout.addLayout(row)

        self.restore_btn = QPushButton("Sicheren Abbruch anfordern")
        self.restore_btn.clicked.connect(self._restore)
        layout.addWidget(self.restore_btn)

        row = QHBoxLayout()
        self.runner_ack_btn = QPushButton("Terminales Ergebnis bestätigen (ACK)")
        self.runner_ack_btn.clicked.connect(self._runner_ack)
        row.addWidget(self.runner_ack_btn)
        self.runner_cleanup_btn = QPushButton("Bestätigten Run aufräumen")
        self.runner_cleanup_btn.clicked.connect(self._runner_cleanup)
        row.addWidget(self.runner_cleanup_btn)
        row.addStretch()
        layout.addLayout(row)

        lifecycle = QLabel(
            "<b>Lebenszyklus:</b> Prepare/Dry-Run → Start → DTU arbeitet autonom → terminales "
            "Ergebnis → ACK → optional Cleanup. Fehler-/Recovery-Runs bleiben bis zur expliziten "
            "Bestätigung für Diagnose erhalten."
        )
        lifecycle.setWordWrap(True)
        layout.addWidget(lifecycle)
        layout.addStretch()
        return widget

    def _prepare_runner(self, *, mode: str, autostart: bool) -> None:
        manifest = Path(self.update_manifest.text().strip())
        if mode == "same-version" and hasattr(self, "same_manifest"):
            candidate = Path(self.same_manifest.text().strip())
            if candidate.is_file():
                manifest = candidate
        if not manifest.is_file():
            QMessageBox.warning(self, "Manifest fehlt", "Bitte zuerst eine gültige Update-Datei auswählen.")
            return

        self._runner_autostart_after_prepare = autostart
        self._runner_prepare_mode = mode
        self._runner_prepared_manifest = None
        self._runner_acknowledged = False
        args = ["prepare", "--manifest", str(manifest), "--mode", mode]
        if hasattr(self, "restart_before_update") and self.restart_before_update.isChecked():
            args.append("--restart-service-before-update")
        if self.isolate_mqtt.isChecked():
            args.append("--isolate-mqtt")
        self._run_runner("runner-prepare", *args)

    def _dry(self):
        if self._runner_active:
            return
        self._reset_flow("DTU-Paket wird geprüft und vorbereitet", transfer_expected=False)
        self._prepare_runner(mode="full", autostart=False)

    def _update_run(self):
        manifest = Path(self.update_manifest.text().strip())
        if not manifest.is_file() or not self.risk.isChecked() or self._runner_active:
            return
        if (
            QMessageBox.warning(
                self,
                "Autonomes Firmwareupdate starten",
                "Das Mainboard-Firmwareupdate wird nach dem Start vollständig vom LTE-Modem "
                "überwacht. Windows/ADB darf danach ausfallen, ohne dass der Runner absichtlich "
                "gestoppt wird.\n\nNach dem Point-of-no-return ist kein sicherer Abbruch mehr "
                "möglich. Wärmepumpe/LTE-Modem während eines laufenden Updates nicht stromlos "
                "machen.\n\nFirmwareupdate jetzt starten?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return

        self._reset_flow("Autonomes Firmwareupdate wird vorbereitet", transfer_expected=True)
        prepared = (
            self._runner_run_id
            and self._runner_prepared_manifest is not None
            and self._runner_prepared_manifest.resolve() == manifest.resolve()
            and not self._runner_terminal
            and not self._runner_active
        )
        if prepared:
            self._start_prepared_runner()
        else:
            self._prepare_runner(mode="full", autostart=True)

    def _same(self):
        if self._runner_active:
            return
        self._reset_flow("Autonomer Gleichversionstest wird vorbereitet", transfer_expected=False)
        self._prepare_runner(mode="same-version", autostart=True)

    def _start_prepared_runner(self) -> None:
        if not self._runner_run_id:
            QMessageBox.critical(self, "DTU Runner", "Kein vorbereiteter Run vorhanden.")
            return
        self._run_runner("runner-start", "start", "--run-id", self._runner_run_id)

    def _status_run(self):
        if self._runner_run_id:
            self._run_runner("runner-status", "status", "--run-id", self._runner_run_id)
        else:
            self._run_runner("runner-current", "current")

    def _runner_log(self):
        if self._runner_run_id:
            self._run_runner("runner-log", "log", "--run-id", self._runner_run_id)
        else:
            self._run_runner("runner-log", "log")

    def _restore(self):
        if not self._runner_run_id:
            QMessageBox.information(
                self, "Abbruch", "Zuerst den aktuellen Runner-Status lesen, damit der Run eindeutig feststeht."
            )
            return
        if not self._runner_abort_allowed:
            QMessageBox.warning(
                self,
                "Abbruch nicht zulässig",
                "Der DTU-Runner meldet abort_allowed=false. Nach dem Point-of-no-return wird "
                "kein erzwungener Restore/Abbruch ausgeführt.",
            )
            return
        if (
            QMessageBox.question(
                self,
                "Sicheren Abbruch anfordern",
                "Die Abbruchanforderung wird persistent an den DTU-Runner geschrieben. "
                "Der Runner entscheidet lokal, ob der sichere Pre-Transfer-Recoverypfad noch "
                "zulässig ist.\n\nAbbruch jetzt anfordern?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        ):
            self._run_runner(
                "runner-abort", "abort-request", "--run-id", self._runner_run_id
            )

    def _runner_ack(self):
        if self._runner_run_id and self._runner_terminal:
            self._run_runner("runner-ack", "ack", "--run-id", self._runner_run_id)

    def _runner_cleanup(self):
        if self._runner_run_id and self._runner_terminal and self._runner_acknowledged:
            if (
                QMessageBox.question(
                    self,
                    "Runner-Diagnose aufräumen",
                    "Der bestätigte Run wird von der DTU entfernt. Das ist nach ACK bewusst "
                    "eine separate Aktion.\n\nRun jetzt aufräumen?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                == QMessageBox.Yes
            ):
                self._run_runner(
                    "runner-cleanup", "cleanup", "--run-id", self._runner_run_id
                )

    def _reattach_ota(self):
        adb = self._require_adb()
        if not adb:
            return
        runner = [
            str(base.backend_python()),
            str(self._runner_cli()),
            "--adb",
            str(adb),
            "current",
        ]
        self._run_sequence(
            "runner-current",
            [[str(adb), "reconnect"], runner],
            str(base.backend_dir()),
        )

    def _poll_runner_status(self):
        if self.busy or not self._runner_active or not self._runner_run_id:
            return
        self._run_runner("runner-status", "status", "--run-id", self._runner_run_id)

    @staticmethod
    def _phase_text(phase: str) -> str:
        return {
            "dry-run-complete": "Paket auf der DTU vollständig geprüft",
            "local-preparation": "DTU-Runner bereitet den Lauf lokal vor",
            "service-restart": "phnixIot4G wird kontrolliert neu gestartet",
            "staging": "Lokale Firmwarebereitstellung wird geprüft",
            "hook-started": "Runtime-Hook gestartet",
            "c350": "C350 gesendet – Mainboardantwort wird ausgewertet",
            "c350-sent": "C350 gesendet – Mainboardantwort wird ausgewertet",
            "accepted": "Mainboard hat das Update angenommen",
            "c357": "C357 übertragen – Firmwaretransfer wird vorbereitet",
            "c5a8": "C5A8-Firmwaretransfer läuft",
            "success-report": "Mainboard meldet Erfolg – Abschlussgrenze wird geprüft",
            "success": "Mainboard-Update terminal erfolgreich",
            "same-version": "Gleiche Firmware erkannt – kein Transfer erforderlich",
            "failed": "Mainboard meldet terminalen Fehler",
            "reboot-detected": "DTU-Reboot während eines nichtterminalen Runs erkannt",
            "orphaned-run": "Nichtterminaler Run ohne nachweisbaren Runner klassifiziert",
        }.get(phase, phase or "unbekannte Phase")

    def _render_runner_status(self, status: dict) -> None:
        run_id = str(status.get("run_id") or "")
        if run_id:
            self._runner_run_id = run_id
        state = str(status.get("state") or "?")
        phase = str(status.get("phase") or "?")
        result_type = str(status.get("result_type") or "")
        terminal = status.get("terminal") is True
        abort_allowed = status.get("abort_allowed") is True
        transfer_started = status.get("transfer_started") is True
        authoritative = status.get("original_service_authoritative") is True
        recovery = str(status.get("recovery") or "?")
        detail = str(status.get("detail") or "")
        progress = status.get("progress")
        board_step = status.get("board_ota_step")

        self._runner_terminal = terminal
        self._runner_active = state == "running" and not terminal
        self._runner_abort_allowed = abort_allowed and not terminal
        if terminal:
            self._runner_timer.stop()
        elif self._runner_active and not self._runner_timer.isActive():
            self._runner_timer.start()

        if isinstance(progress, int):
            self.progress.setValue(max(0, min(100, progress)))
            self.progress.setFormat(f"{max(0, min(100, progress))} % – DTU-Runner")
        self.progress_text.setText(self._phase_text(phase))
        if hasattr(self, "progress_sources"):
            extra = f"Run: {run_id or '?'} | Zustand: {state} | Recovery: {recovery}"
            if isinstance(board_step, int) and board_step:
                extra += f" | Board-Step: {board_step}"
            self.progress_sources.setText(extra)

        if phase == "dry-run-complete":
            self._set_step("runner-preflight", "ok", "Paket, Hashes, Speicher, Service-Build und DTU-Voraussetzungen geprüft.")
        if status.get("c350_sent") is True:
            self._set_step("runner-c350", "ok", "C350 wurde vom DTU-Runner gesendet.")
        if status.get("c357_sent") is True:
            self._set_step("runner-c357", "ok", "C357 wurde vom DTU-Runner gesendet.")
        if status.get("c5a8_sent") is True or transfer_started:
            self._set_step("runner-c5a8", "warn", "C5A8 hat begonnen – Point-of-no-return erreicht; kein sicherer Abbruch mehr.")
        if authoritative:
            self._set_step("runner-authority", "info", "Der originale PHNIX-Dienst ist für den weiteren OTA-Ablauf autoritativ.")
        if terminal:
            level = "ok" if result_type in {"success", "same-version"} else "warn"
            if result_type in {"failed", "recovery-required", "reboot-detected", "orphaned"}:
                level = "error"
            self._set_step("runner-terminal", level, f"Terminales Runner-Ergebnis: {result_type or phase}.")

        abort_text = "ja" if self._runner_abort_allowed else "nein"
        transfer_text = "ja" if transfer_started else "nein"
        authority_text = "ja" if authoritative else "nein"
        terminal_text = "ja" if terminal else "nein"
        self.status_text.setText(
            f"<b>Run:</b> <code>{escape(run_id or '?')}</code><br>"
            f"<b>Zustand:</b> {escape(state)}<br>"
            f"<b>Phase:</b> {escape(self._phase_text(phase))}<br>"
            f"<b>Terminal:</b> {terminal_text}"
            + (f" – <b>{escape(result_type)}</b>" if result_type else "")
            + f"<br><b>Transfer begonnen:</b> {transfer_text}<br>"
            f"<b>Originaldienst autoritativ:</b> {authority_text}<br>"
            f"<b>Sicherer Abbruch erlaubt:</b> {abort_text}<br>"
            f"<b>Recovery:</b> {escape(recovery)}"
            + (f"<br><br>{escape(detail)}" if detail else "")
        )
        self.ota_reattach_btn.setVisible(self._runner_active or bool(self._runner_run_id))
        self._buttons()

        if terminal and run_id and run_id not in self._runner_terminal_notified:
            self._runner_terminal_notified.add(run_id)
            self._show_terminal_result(result_type, phase, detail)

    def _show_terminal_result(self, result_type: str, phase: str, detail: str) -> None:
        result = result_type or phase
        if result == "success":
            self._flow_title = "Firmwareupdate erfolgreich"
            self.progress.setValue(100)
            self.progress.setFormat("100 % – terminal erfolgreich")
            QMessageBox.information(
                self,
                "Firmwareupdate erfolgreich",
                "Der DTU-Runner hat den Mainboard-Erfolg und die terminale Step-12-Grenze bestätigt.",
            )
        elif result == "same-version":
            self._flow_title = "Kein Firmwareupdate erforderlich"
            QMessageBox.information(
                self,
                "Gleiche Firmware erkannt",
                "Das Mainboard hat die gleiche Firmware erkannt. Es wurde kein C5A8-Firmwaretransfer gestartet.",
            )
        elif result == "aborted-before-transfer":
            self._flow_title = "Update sicher vor Transfer abgebrochen"
            QMessageBox.warning(self, "Update abgebrochen", "Der sichere Pre-Transfer-Abbruch wurde terminal bestätigt.")
        elif result == "recovery-completed":
            self._flow_title = "Recovery abgeschlossen"
            QMessageBox.warning(self, "Recovery abgeschlossen", detail or "Der DTU-Runner hat den sicheren Recoverypfad abgeschlossen.")
        else:
            self._flow_title = "DTU-Runner meldet Diagnosebedarf"
            QMessageBox.critical(
                self,
                "Firmwareupdate nicht erfolgreich abgeschlossen",
                f"Terminales Ergebnis: {result or '?'}\n\n{detail or 'Diagnose auf der DTU erhalten; keinen blinden Restore ausführen.'}",
            )
        self._render_flow()

    def _done(self, op, code, output):
        if not op.startswith("runner-"):
            super()._done(op, code, output)
            return

        super()._done("handled-result", code, output)

        if op == "runner-log":
            if code != 0:
                QMessageBox.warning(self, "Runner-Log", "Runner-Log konnte nicht gelesen werden.")
            return

        if op == "runner-cleanup":
            if code == 0:
                self._log("[DTU Runner] bestätigter Run wurde aufgeräumt.")
                self._runner_run_id = None
                self._runner_prepared_manifest = None
                self._runner_active = False
                self._runner_terminal = False
                self._runner_abort_allowed = False
                self._runner_acknowledged = False
                self.ota_reattach_btn.setVisible(False)
                self.status_text.setText("Bestätigter Run wurde aufgeräumt.")
                self._buttons()
            else:
                QMessageBox.critical(self, "Cleanup", "Runner-Cleanup fehlgeschlagen. Diagnose bleibt erhalten.")
            return

        status = self._runner_json(output)
        if code != 0 or status is None or status.get("ok") is False:
            if op in {"runner-status", "runner-current"} and self._runner_active:
                self.progress_text.setText(
                    "ADB-Verbindung nicht verfügbar – DTU-Runner arbeitet autonom weiter."
                )
                self._set_step(
                    "runner-adb-lost",
                    "warn",
                    "Windows kann den Runner momentan nicht lesen; auf der DTU wird nichts gestoppt oder restored.",
                )
                self.ota_reattach_btn.setVisible(True)
                self._render_flow()
                return
            QMessageBox.critical(
                self,
                "DTU Runner",
                "Runner-Befehl fehlgeschlagen. Details stehen im Protokoll."
                + (f"\n\n{status.get('error')}" if isinstance(status, dict) and status.get("error") else ""),
            )
            return

        if op == "runner-prepare":
            self._runner_run_id = str(status.get("run_id") or "") or None
            manifest = Path(self.update_manifest.text().strip())
            if self._runner_prepare_mode == "same-version" and hasattr(self, "same_manifest"):
                candidate = Path(self.same_manifest.text().strip())
                if candidate.is_file():
                    manifest = candidate
            self._runner_prepared_manifest = manifest if manifest.is_file() else None
            self._render_runner_status(status)
            if status.get("phase") != "dry-run-complete":
                QMessageBox.critical(self, "DTU-Vorprüfung", "Die DTU hat den Prepare/Dry-Run nicht bestätigt.")
                self._runner_autostart_after_prepare = False
                return
            self._set_step("runner-prepared", "ok", "Run ist persistent auf der DTU vorbereitet; noch kein GDB-Attach und kein C350.")
            if self._runner_autostart_after_prepare:
                self._runner_autostart_after_prepare = False
                QTimer.singleShot(150, self._start_prepared_runner)
            else:
                QMessageBox.information(
                    self,
                    "DTU-Vorprüfung erfolgreich",
                    "Paket und lokale Voraussetzungen wurden auf der DTU vollständig geprüft. "
                    "Es wurde kein GDB-Attach und kein Mainboard-OTA gestartet.",
                )
            return

        if op in {"runner-start", "runner-status", "runner-current", "runner-abort", "runner-ack"}:
            self._render_runner_status(status)
            if op == "runner-start":
                self._runner_active = status.get("terminal") is not True
                if self._runner_active and not self._runner_timer.isActive():
                    self._runner_timer.start()
                self._set_step("runner-detached", "ok", "DTU-Runner wurde detached gestartet; Windows ist nur noch Status-Client.")
            elif op == "runner-abort":
                self._set_step("runner-abort-request", "warn", "Abbruchanforderung wurde an den DTU-Runner geschrieben; die lokale Phasengrenze entscheidet.")
            elif op == "runner-ack":
                self._runner_acknowledged = True
                self._log("[DTU Runner] terminales Ergebnis wurde bestätigt (ACK).")
                self._buttons()
            return

    def _buttons(self):
        super()._buttons()
        if not hasattr(self, "status_btn"):
            return
        enabled = not self.busy
        adb_ready = self._adb_ready()
        manifest_ready = Path(self.update_manifest.text().strip()).is_file()
        if self._runner_active:
            self.dry.setEnabled(False)
            self.update_btn.setEnabled(False)
        else:
            self.dry.setEnabled(enabled and adb_ready and manifest_ready)
            self.update_btn.setEnabled(enabled and adb_ready and manifest_ready and self.risk.isChecked())
        self.status_btn.setEnabled(enabled and adb_ready)
        self.runner_log_btn.setEnabled(enabled and adb_ready)
        self.restore_btn.setEnabled(enabled and adb_ready and self._runner_abort_allowed)
        self.runner_ack_btn.setEnabled(enabled and adb_ready and self._runner_terminal)
        self.runner_cleanup_btn.setEnabled(
            enabled and adb_ready and self._runner_terminal and self._runner_acknowledged
        )
        self.ota_reattach_btn.setEnabled(enabled and adb_ready)


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
