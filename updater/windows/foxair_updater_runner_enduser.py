from __future__ import annotations

import sys
import time
from datetime import datetime
from html import escape
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import foxair_updater_gui as base
import foxair_updater_runner_user_gui as user_gui


class MainWindow(user_gui.MainWindow):
    """Final end-user presentation for the autonomous DTU runner.

    This layer deliberately does not change runner decisions.  It restores the
    proven Windows presentation features from the previous controller GUI:
    automatic controller/LTE logs beside the firmware, dual progress sources,
    source fallback and a more detailed visible phase history.
    """

    def __init__(self):
        self._runner_log_run_id: str | None = None
        self._runner_progress_value: float | None = None
        self._runner_progress_offset: int | None = None
        self._runner_progress_length: int | None = None
        self._runner_transfer_visible = False
        self._runner_result_type = ""
        self._runner_recovery_state = ""
        self._passive_runner_poll = False
        self._runner_started_epoch: int | None = None
        self._runner_terminal_epoch: int | None = None
        super().__init__()
        # The DTU itself refreshes OTA_INFO every two seconds. Poll at the same
        # cadence so the Windows fallback display does not lag several seconds
        # behind the autonomous runner state.
        self._runner_timer.setInterval(2000)
        self.setWindowTitle(f"FoxAir Updater {base.APP_VERSION}")
        self.dry.setText("Vorprüfung")
        self.update_btn.setText("Firmwareupdate starten")
        self._log(f"[FoxAir Updater] Version {base.APP_VERSION} – autonomer DTU-Runner")

    # ------------------------------------------------------------------
    # Firmware page polish
    # ------------------------------------------------------------------
    def _update(self):
        widget = super()._update()
        layout = widget.layout()
        self.ota_reattach_btn.setText("Status prüfen")
        self.ota_reattach_btn.setToolTip(
            "Liest den gespeicherten Update-Status vom LTE-Modem. Falls die ADB-Verbindung "
            "unterbrochen wurde, wird sie dabei neu aufgebaut."
        )
        # The status action is secondary to the actual update controls. Keep it
        # at the bottom of the firmware page instead of between progress and
        # prepare/start controls.
        layout.removeWidget(self.ota_reattach_btn)
        layout.insertWidget(max(0, layout.count() - 1), self.ota_reattach_btn)
        return widget

    def _poll_runner_status(self):
        if self.busy or not self._runner_active or not self._runner_run_id:
            return
        # Automatic polling must not make the visible manual status button flash
        # disabled/enabled every few seconds. The command still uses the normal
        # runner path; only the presentation of this button stays stable.
        self._passive_runner_poll = True
        self._run_runner("runner-status", "status", "--run-id", self._runner_run_id)

    def _buttons(self):
        super()._buttons()
        if not hasattr(self, "ota_reattach_btn"):
            return

        if self._passive_runner_poll and self._adb_ready():
            self.ota_reattach_btn.setEnabled(True)

        if not hasattr(self, "runner_cleanup_btn"):
            return
        retain_diagnostics = (
            self._runner_recovery_state == "required"
            or self._runner_result_type in {"recovery-required", "reboot-detected"}
        )
        if retain_diagnostics:
            self.runner_cleanup_btn.setText("Diagnosedaten werden beibehalten")
            self.runner_cleanup_btn.setToolTip(
                "Dieses Ergebnis benötigt eine manuelle Prüfung. Die Diagnosedaten werden deshalb "
                "absichtlich nicht automatisch gelöscht. Die Ergebnisbestätigung bestätigt nur, "
                "dass der Hinweis gesehen wurde."
            )
            self.runner_cleanup_btn.setEnabled(False)
        else:
            self.runner_cleanup_btn.setText("Gespeicherte Updatedaten löschen")
            self.runner_cleanup_btn.setToolTip(
                "Löscht erst nach der Ergebnisbestätigung die gespeicherten Daten dieses "
                "Firmwareupdates vom LTE-Modem."
            )

    # ------------------------------------------------------------------
    # Runner elapsed time
    # ------------------------------------------------------------------
    def _reset_flow(self, title: str, *, transfer_expected: bool = False):
        self._runner_started_epoch = None
        self._runner_terminal_epoch = None
        return super()._reset_flow(title, transfer_expected=transfer_expected)

    def _update_ota_elapsed(self) -> None:
        if self._runner_started_epoch is None:
            super()._update_ota_elapsed()
            return
        if not hasattr(self, "ota_elapsed_label"):
            return
        end_epoch = self._runner_terminal_epoch
        if end_epoch is None:
            end_epoch = int(time.time())
        elapsed = max(0, int(end_epoch - self._runner_started_epoch))
        minutes, seconds = divmod(elapsed, 60)
        self.ota_elapsed_label.setText(f"Verstrichen: {minutes:02d}:{seconds:02d}")

    def _sync_runner_elapsed(self, status: dict) -> None:
        state = str(status.get("state") or "")
        terminal = status.get("terminal") is True
        started_at = status.get("started_at")
        if not isinstance(started_at, int) or started_at <= 0:
            return
        if state != "running" and not terminal:
            return

        self._runner_started_epoch = started_at
        if terminal:
            updated_at = status.get("updated_at")
            self._runner_terminal_epoch = (
                updated_at if isinstance(updated_at, int) and updated_at >= started_at else int(time.time())
            )
            self._ota_elapsed_timer.stop()
        else:
            self._runner_terminal_epoch = None
            if not self._ota_elapsed_timer.isActive():
                self._ota_elapsed_timer.start()
        self._update_ota_elapsed()

    # ------------------------------------------------------------------
    # Automatic update logs
    # ------------------------------------------------------------------
    def _write_automatic_log_only(self, text: str) -> None:
        """Write a timestamped line only to the automatic controller log."""
        automatic_log = getattr(self, "_automatic_log", None)
        if automatic_log is None:
            return
        try:
            stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            automatic_log.write(f"[{stamp}] {text}\n")
            automatic_log.flush()
        except OSError as error:
            self._automatic_log = None
            super()._log(
                f"[Warnung] Automatisches Controller-Log konnte nicht weitergeschrieben werden: {error}"
            )

    def _log(self, text):
        """Keep the on-screen protocol unchanged, but timestamp every automatic log line."""
        automatic_log = getattr(self, "_automatic_log", None)
        if automatic_log is None:
            super()._log(text)
            return

        # The inherited implementation also writes to _automatic_log. Temporarily
        # hide that stream so the GUI protocol is still handled normally without
        # duplicating the file entry, then write the timestamped file line here.
        self._automatic_log = None
        try:
            super()._log(text)
        finally:
            self._automatic_log = automatic_log

        try:
            lines = str(text).splitlines() or [""]
            for line in lines:
                stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                automatic_log.write(f"[{stamp}] {line}\n")
            automatic_log.flush()
        except OSError as error:
            self._automatic_log = None
            super()._log(
                f"[Warnung] Automatisches Controller-Log konnte nicht weitergeschrieben werden: {error}"
            )

    def _run_runner(self, op: str, *args: str) -> None:
        # Use exactly the established automatic logging implementation from the
        # previous GUI.  It creates:
        #   <firmware-dir>/Logs/FoxAir_Update_<timestamp>.log
        #   <firmware-dir>/Logs/FoxAir_Update_<timestamp>_LTE.log
        # and falls back to the firmware directory only if Logs cannot be used.
        if op == "runner-prepare":
            manifest = None
            try:
                index = args.index("--manifest")
                candidate = Path(args[index + 1])
                if candidate.is_file():
                    manifest = candidate
            except (ValueError, IndexError, TypeError):
                pass
            if manifest is not None:
                self._start_automatic_logs(manifest)
                self._runner_log_run_id = None
                self._runner_progress_value = None
                self._runner_progress_offset = None
                self._runner_progress_length = None
                self._runner_transfer_visible = False
                self._runner_started_epoch = None
                self._runner_terminal_epoch = None
                # The version is already shown once in the visible protocol at
                # application start. Put it into the newly opened automatic log
                # directly so the GUI does not show the same header twice.
                self._write_automatic_log_only(
                    f"[FoxAir Updater] Version {base.APP_VERSION} – autonomer DTU-Runner"
                )
                self._log(f"[Update-Log] Firmware-Verzeichnis: {manifest.parent}")
        super()._run_runner(op, *args)

    def _log_runner_id_once(self, run_id: str) -> None:
        if not run_id or run_id == self._runner_log_run_id:
            return
        self._runner_log_run_id = run_id
        self._log(f"[DTU Runner] Lauf-ID: {run_id}")

    # ------------------------------------------------------------------
    # User-facing phases / flow history
    # ------------------------------------------------------------------
    @staticmethod
    def _phase_text(phase: str) -> str:
        friendly = {
            "attaching": "Update-Überwachung wird mit dem LTE-Dienst verbunden",
            "hook-ended-before-authority": (
                "Update-Überwachung vor Beginn beendet – Originalzustand wiederhergestellt"
            ),
            "original-service-active-unmonitored": (
                "Firmwareupdate läuft auf dem LTE-Modem weiter – lokale Überwachung ist beendet"
            ),
            "post-restart-preflight": "LTE-Dienst wird nach dem Neustart erneut geprüft",
            "local-http": "Firmwaredatei wird für das LTE-Modem bereitgestellt",
            "invalid-success-boundary": "Abschluss des Firmwareupdates konnte noch nicht sicher bestätigt werden",
            "invalid-failure-boundary": "Fehlerstatus des Firmwareupdates konnte noch nicht sicher bestätigt werden",
        }
        return friendly.get(phase, user_gui.MainWindow._phase_text(phase))

    @staticmethod
    def _friendly_detail(status: dict) -> str:
        phase = str(status.get("phase") or "")
        reason = str(status.get("reason") or "")
        detail = str(status.get("detail") or "").strip()

        phase_text = {
            "dry-run-complete": (
                "Die Vorprüfung ist abgeschlossen. Das Firmwareupdate ist vorbereitet, aber noch nicht gestartet."
            ),
            "local-preparation": "Das LTE-Modem bereitet das Firmwareupdate vor.",
            "service-restart": "Der LTE-Kommunikationsdienst wird für die Update-Überwachung neu gestartet.",
            "same-version": "Die gleiche Firmware ist bereits installiert. Es wurden keine Firmwaredaten übertragen.",
            "original-service-active-unmonitored": (
                "Das Firmwareupdate läuft auf dem LTE-Modem weiter. Windows kann den aktuellen Stand "
                "momentan nicht vollständig überwachen."
            ),
            "hook-ended-before-authority": (
                "Das Firmwareupdate wurde vor Beginn der Übertragung beendet und der Originalzustand wiederhergestellt."
            ),
            "reboot-detected": (
                "Das LTE-Modem wurde während des Firmwareupdates neu gestartet. Eine manuelle Prüfung ist erforderlich."
            ),
        }.get(phase)
        if phase_text:
            return phase_text

        reason_text = {
            "package_validation_failed": "Die Vorprüfung der Update-Datei oder des LTE-Modems ist fehlgeschlagen.",
            "hook_monitor_lost": "Die lokale Update-Überwachung wurde unterbrochen. Bitte den gespeicherten Status prüfen.",
            "active_run_exists": "Auf dem LTE-Modem ist bereits ein Firmwareupdate aktiv.",
        }.get(reason)
        if reason_text:
            return reason_text

        technical_markers = (
            "gdb", "c350", "c357", "c5a8", "c36e", "hook", "runner", "ota_info",
            "abort_allowed", "original_service", "point-of-no-return", "/data/", "step 12",
        )
        if detail and not any(marker in detail.lower() for marker in technical_markers):
            return detail
        if detail:
            return "Technische Details stehen im Protokoll."
        return ""

    def _update_flow_from_runner(self, status: dict) -> None:
        phase = str(status.get("phase") or "")
        terminal = status.get("terminal") is True
        result_type = str(status.get("result_type") or "")
        transfer_started = status.get("transfer_started") is True
        authoritative = status.get("original_service_authoritative") is True

        # Replace the technical protocol labels created by the lower runner
        # layer with end-user wording. Reusing the same flow keys updates the
        # existing rows instead of adding duplicate C350/C357/C5A8 entries.
        if status.get("c350_sent") is True:
            self._set_step(
                "runner-c350", "ok",
                "Update-Anfrage wurde an das Mainboard gesendet.",
            )
        if status.get("c357_sent") is True:
            self._set_step(
                "runner-c357", "ok",
                "Firmwareübertragung wurde vorbereitet.",
            )
        if status.get("c5a8_sent") is True or transfer_started:
            self._set_step(
                "runner-c5a8", "warn",
                "Firmwareübertragung hat begonnen – ein sicherer Abbruch ist jetzt nicht mehr möglich.",
            )
        if authoritative:
            self._set_step(
                "runner-authority", "info",
                "Das LTE-Modem führt das Firmwareupdate jetzt selbstständig weiter.",
            )

        phase_steps = {
            "dry-run-complete": (
                "runner-preflight-user", "ok",
                "Update-Datei, Speicherplatz und LTE-Modem wurden erfolgreich geprüft.",
            ),
            "local-preparation": (
                "runner-local-preparation", "ok",
                "Firmwareupdate wurde auf dem LTE-Modem vorbereitet.",
            ),
            "service-restart": (
                "runner-service-restart", "warn",
                "LTE-Kommunikationsdienst wird für die Update-Überwachung neu gestartet.",
            ),
            "staging": (
                "runner-staging", "ok",
                "Firmwaredatei wird für das Update geprüft.",
            ),
            "hook-started": (
                "runner-monitor", "ok",
                "Update-Überwachung auf dem LTE-Modem wurde gestartet.",
            ),
            "hook-starting": (
                "runner-monitor", "warn",
                "Update-Überwachung auf dem LTE-Modem wird gestartet.",
            ),
            "attaching": (
                "runner-monitor", "warn",
                "Update-Überwachung verbindet sich mit dem LTE-Dienst.",
            ),
            "waiting-for-yield-loop": (
                "runner-yield", "warn",
                "Sicherer Start des Firmwareupdates wird abgewartet.",
            ),
            "parser-injection": (
                "runner-parser", "warn",
                "Firmwareupdate wird an das Mainboard übergeben.",
            ),
            "accepted": (
                "runner-accepted-user", "ok",
                "Mainboard hat das Firmwareupdate angenommen.",
            ),
            "success-report": (
                "runner-success-report", "ok",
                "Firmware vollständig übertragen – das Mainboard prüft und übernimmt das Update.",
            ),
            "same-version": (
                "runner-same-user", "ok",
                "Gleiche Firmware erkannt; es wurden keine Firmwaredaten übertragen.",
            ),
            "hook-ended-before-authority": (
                "runner-recovery-user", "warn",
                "Update wurde vor Beginn der Übertragung beendet; Originalzustand wurde wiederhergestellt.",
            ),
        }
        item = phase_steps.get(phase)
        if item:
            self._set_step(*item)

        if terminal:
            if result_type == "success":
                self._set_step(
                    "runner-terminal-user", "ok",
                    "Firmwareupdate wurde erfolgreich abgeschlossen.",
                )
            elif result_type == "same-version":
                self._set_step(
                    "runner-terminal-user", "ok",
                    "Gleiche Firmware sicher erkannt; kein Firmwareupdate erforderlich.",
                )
            elif result_type == "recovery-completed":
                self._set_step(
                    "runner-terminal-user", "warn",
                    "Originalzustand wurde erfolgreich wiederhergestellt.",
                )
            elif result_type == "aborted-before-transfer":
                self._set_step(
                    "runner-terminal-user", "warn",
                    "Firmwareupdate wurde sicher vor Beginn der Übertragung abgebrochen.",
                )
            elif result_type in {"recovery-required", "reboot-detected"}:
                self._set_step(
                    "runner-terminal-user", "error",
                    "Manuelle Prüfung erforderlich; Diagnosedaten bleiben auf dem LTE-Modem erhalten.",
                )

    def _finalize_success_flow(self) -> None:
        """Turn transient warning/info steps into completed green success steps."""
        replacements = {
            "runner-monitor": "Update-Überwachung auf dem LTE-Modem wurde gestartet.",
            "runner-yield": "Sicherer Start des Firmwareupdates wurde erreicht.",
            "runner-parser": "Firmwareupdate wurde an das Mainboard übergeben.",
            "runner-service-restart": "LTE-Kommunikationsdienst wurde kontrolliert neu gestartet.",
            "runner-c350": "Update-Anfrage wurde an das Mainboard gesendet.",
            "runner-c357": "Firmwareübertragung wurde vorbereitet.",
            "runner-c5a8": "Firmware wurde vollständig an das Mainboard übertragen.",
            "runner-authority": "Das LTE-Modem hat den weiteren Updateablauf übernommen.",
            "runner-success-report": "Mainboard hat das Update erfolgreich übernommen.",
            "runner-terminal": "Firmwareupdate erfolgreich abgeschlossen.",
            "runner-terminal-user": "Firmwareupdate wurde erfolgreich abgeschlossen.",
        }
        for key, (level, text) in list(self._flow_steps.items()):
            if level in {"warn", "info"}:
                self._flow_steps[key] = ("ok", replacements.get(key, text))
        for key, text in replacements.items():
            if key in self._flow_steps:
                self._flow_steps[key] = ("ok", text)
        self._render_flow()

    # ------------------------------------------------------------------
    # Dual transfer progress: serial PHNIX log + autonomous runner
    # ------------------------------------------------------------------
    def _render_transfer_progress(self) -> None:
        """Restore the previous dual-source progress behavior.

        PHNIX serial progress is preferred for the bar while it is available.
        If that source disappears, the inherited debug status handling clears
        ``_phnix_transfer_event`` and the runner value automatically becomes the
        displayed fallback.  Both values are listed below the bar whenever both
        are available.
        """
        event = self._phnix_transfer_event
        runner_percent = self._runner_progress_value
        runner_offset = self._runner_progress_offset
        runner_length = self._runner_progress_length

        lines: list[str] = []
        display_percent: float | int | None = None

        if event is not None:
            serial_percent = float(event.progress)
            display_percent = serial_percent
            lines.append(
                (
                    f"LTE-Dienst: {serial_percent:.1f} % · "
                    f"{event.current:,} / {event.total:,} Byte"
                ).replace(",", ".")
            )

        if runner_percent is not None and self._runner_transfer_visible:
            if display_percent is None:
                display_percent = runner_percent
            if (
                isinstance(runner_offset, int)
                and isinstance(runner_length, int)
                and runner_length > 0
            ):
                lines.append(
                    (
                        f"LTE-Modem: {runner_percent:.1f} % · "
                        f"{runner_offset:,} / {runner_length:,} Byte"
                    ).replace(",", ".")
                )
            else:
                lines.append(f"LTE-Modem: {runner_percent:.1f} %")

        if display_percent is not None:
            value = max(0, min(100, round(display_percent)))
            self.progress.setValue(value)
            # No text inside the bar. The separate percent label remains next to
            # it; detailed source values stay below the bar.
            self.progress.setFormat("")
            if hasattr(self, "progress_percent_label"):
                self.progress_percent_label.setText(f"{float(display_percent):.1f} %")
        else:
            self.progress.setValue(0)
            self.progress.setFormat("")
            if hasattr(self, "progress_percent_label"):
                self.progress_percent_label.setText("–")

        if hasattr(self, "progress_sources"):
            self.progress_sources.setText("\n".join(lines))

    # ------------------------------------------------------------------
    # Terminal presentation
    # ------------------------------------------------------------------
    def _show_terminal_result(self, result_type: str, phase: str, detail: str) -> None:
        result = result_type or phase
        if result != "success":
            super()._show_terminal_result(result_type, phase, detail)
            return

        # Do not open a modal dialog while the inherited status renderer is still
        # running. Otherwise the user sees the temporary technical base-layer
        # state behind the popup until OK is clicked. Prepare the final view now
        # and show the success dialog on the next event-loop turn.
        self._flow_title = "Firmwareupdate erfolgreich"
        self.progress.setValue(100)
        self.progress.setFormat("")
        self._render_flow()
        QTimer.singleShot(0, self._show_success_dialog)

    def _show_success_dialog(self) -> None:
        box = user_gui.QMessageBox(self)
        box.setWindowTitle("Firmwareupdate erfolgreich")
        box.setIcon(user_gui.QMessageBox.NoIcon)
        box.setText(
            '<span style="font-size:24px;color:#16803a;"><b>✓</b></span> '
            '<span style="font-size:16px;color:#16803a;"><b>Firmwareupdate erfolgreich</b></span>'
        )
        box.setInformativeText(
            "Das Mainboard-Firmwareupdate wurde erfolgreich abgeschlossen.\n\n"
            "Der Abschluss wurde durch das LTE-Modem bestätigt."
        )
        box.setStandardButtons(user_gui.QMessageBox.Ok)
        box.setDefaultButton(user_gui.QMessageBox.Ok)
        box.setStyleSheet(
            "QMessageBox{background-color:#f4fbf6;}"
            "QLabel{min-width:430px;}"
            "QPushButton{min-width:90px;padding:6px 18px;background:#16803a;"
            "color:white;border:1px solid #126b31;border-radius:4px;font-weight:bold;}"
            "QPushButton:hover{background:#126b31;}"
        )
        box.exec()

    def _render_runner_status(self, status: dict) -> None:
        # Store the terminal classification before the inherited renderer calls
        # _buttons(), so recovery-required runs never briefly enable Cleanup.
        self._runner_result_type = str(status.get("result_type") or "")
        self._runner_recovery_state = str(status.get("recovery") or "?")

        # Let the established runner layer update all lifecycle/safety state and
        # buttons first. The success popup is deferred by our override above, so
        # the final end-user rendering below completes before a dialog is shown.
        super()._render_runner_status(status)

        run_id = str(status.get("run_id") or "")
        state = str(status.get("state") or "?")
        phase = str(status.get("phase") or "?")
        result_type = self._runner_result_type
        terminal = status.get("terminal") is True
        transfer_started = status.get("transfer_started") is True
        authoritative = status.get("original_service_authoritative") is True
        recovery = self._runner_recovery_state
        detail = self._friendly_detail(status)
        progress = status.get("progress")
        offset = status.get("offset")
        length = status.get("length")

        self._sync_runner_elapsed(status)
        self._log_runner_id_once(run_id)
        self._update_flow_from_runner(status)
        if terminal and result_type == "success":
            self._finalize_success_flow()

        if isinstance(offset, int):
            self._runner_progress_offset = offset
        if isinstance(length, int):
            self._runner_progress_length = length

        if (
            isinstance(self._runner_progress_offset, int)
            and isinstance(self._runner_progress_length, int)
            and self._runner_progress_length > 0
        ):
            precise = self._runner_progress_offset * 100.0 / self._runner_progress_length
            self._runner_progress_value = max(0.0, min(100.0, precise))
        elif isinstance(progress, (int, float)):
            self._runner_progress_value = max(0.0, min(100.0, float(progress)))

        self._runner_transfer_visible = bool(
            transfer_started
            or phase == "c5a8"
            or (isinstance(length, int) and length > 0)
        )

        transfer_complete_waiting = bool(
            not terminal
            and isinstance(offset, int)
            and isinstance(length, int)
            and length > 0
            and offset >= length
        )

        if self._runner_transfer_visible:
            self._render_transfer_progress()
            if transfer_complete_waiting:
                self.progress_text.setText("Firmware vollständig übertragen – bitte warten")
                if hasattr(self, "progress_sources"):
                    current = self.progress_sources.text().strip()
                    note = "Mainboard verarbeitet und prüft das Update – bitte warten …"
                    self.progress_sources.setText((current + "\n" if current else "") + note)
        else:
            # Before C5A8 there is no meaningful percentage. Same-version and
            # recovery runs therefore no longer show a misleading "0 % DTU Runner".
            self.progress.setValue(0)
            self.progress.setFormat("")
            if hasattr(self, "progress_percent_label"):
                self.progress_percent_label.setText("–")
            if hasattr(self, "progress_sources"):
                self.progress_sources.setText(self._phase_text(phase))

        if terminal and result_type == "success":
            self.progress_text.setText("Firmwareupdate erfolgreich abgeschlossen")

        # Re-render the status box without technical run/protocol details. The
        # complete runner JSON is still written to the technical log.
        if terminal:
            headline = f"<b>Abgeschlossen:</b> {escape(self._result_text(result_type, phase))}"
        elif state == "prepared":
            headline = "<b>Bereit:</b> Vorprüfung abgeschlossen; Firmwareupdate wurde noch nicht gestartet."
        elif state == "running":
            headline = "<b>Firmwareupdate läuft auf dem LTE-Modem.</b>"
        else:
            headline = f"<b>Zustand:</b> {escape(state)}"

        abort_text = "möglich" if self._runner_abort_allowed else "nicht möglich"
        transfer_text = "gestartet" if transfer_started else "noch nicht gestartet"
        notices: list[str] = []
        if authoritative and not (terminal and result_type == "success"):
            notices.append(
                "<b>Hinweis:</b> Das LTE-Modem führt das Update jetzt selbstständig weiter; "
                "ein sicherer Abbruch ist ab dieser Grenze nicht mehr möglich."
            )
        if recovery == "required" or result_type in {"recovery-required", "reboot-detected"}:
            notices.append(
                "<b>Diagnose:</b> Dieses Ergebnis benötigt eine manuelle Prüfung. Die "
                "Diagnosedaten werden deshalb absichtlich beibehalten."
            )
        extra = "".join(f"<br>{item}" for item in notices)

        if terminal and result_type == "success":
            self.runner_status_text.setText(
                "<b>Firmwareupdate erfolgreich abgeschlossen.</b>"
                "<br>Firmware und Mainboard-Abschluss wurden bestätigt."
                "<br>Wiederherstellung ist nicht erforderlich."
            )
        else:
            self.runner_status_text.setText(
                headline
                + f"<br><b>Aktueller Schritt:</b> {escape(self._phase_text(phase))}"
                + f"<br><b>Firmwareübertragung:</b> {transfer_text}"
                + f"<br><b>Sicherer Abbruch:</b> {abort_text}"
                + f"<br><b>Wiederherstellung:</b> {escape(self._recovery_text(recovery))}"
                + extra
                + (f"<br><br>{escape(detail)}" if detail else "")
            )

        # Re-apply the end-user cleanup policy after the status box update.
        self._buttons()

        if terminal:
            # Final runner JSON has already passed through _line() and therefore
            # reached the automatic controller log. It is now safe to close both
            # established automatic log streams.
            QTimer.singleShot(0, self._finish_automatic_logs)

    def _done(self, op, code, output):
        passive_poll = op == "runner-status" and self._passive_runner_poll
        super()._done(op, code, output)
        if passive_poll:
            self._passive_runner_poll = False
            self._buttons()
        if op == "runner-prepare" and code != 0 and not self._runner_run_id:
            self._finish_automatic_logs()


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
