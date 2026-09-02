from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
)

import foxair_updater_gui as base
import foxair_updater_runner_enduser as enduser
from updater.common.phnix_modem_info import PhnixModemInfo


STATISTICS_CONFIRM_TOKEN = "PHNIX-STATISTICS-WRITE"
STATISTICS_FIELDS = (
    ("dtu_ota", "DTU-OTA-Vorgänge", "--dtu-ota-count"),
    ("mainboard_ota", "Mainboard OTA-Vorgänge", "--mainboard-ota-count"),
    ("power_reset", "Dienststarts (Power-Reset-t)", "--power-reset-count"),
    ("active_reset", "Aktive Modem-Neustarts (Active-Reset-t)", "--active-reset-count"),
)


class MainWindow(enduser.MainWindow):
    """Final Windows product glue for the autonomous DTU runner.

    Keeps release-specific path wiring and serial-progress fallback out of the
    generic runner layers. The actual OTA decisions stay in the DTU runner.
    """

    SERIAL_PROGRESS_STALE_SECONDS = 15.0
    FLOW_KEY_ALIASES = {
        # The lower runner layer already creates these rows. Re-use those keys
        # so the end-user wording updates the existing row instead of adding an
        # identical second bullet.
        "runner-preflight-user": "runner-preflight",
        "runner-terminal-user": "runner-terminal",
    }

    def __init__(self):
        self._serial_progress_seen_at: float | None = None
        super().__init__()
        self._serial_progress_watchdog = QTimer(self)
        self._serial_progress_watchdog.setInterval(5000)
        self._serial_progress_watchdog.timeout.connect(self._expire_stale_serial_progress)
        self._serial_progress_watchdog.start()

    def _runner_cli(self) -> Path:
        """Use the production runner package after the repository relocation."""
        return base.backend_dir() / "updater/dtu_ota/cli.py"

    # ------------------------------------------------------------------
    # Final layout polish
    # ------------------------------------------------------------------
    @staticmethod
    def _layout_containing(layout, widget):
        if layout is None:
            return None
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item.widget() is widget:
                return layout
            child = item.layout()
            if child is not None:
                found = MainWindow._layout_containing(child, widget)
                if found is not None:
                    return found
        return None

    def _ui(self):
        super()._ui()

        # The manifest editor is an occasional maintenance tool. Keep it close
        # to Advanced instead of interrupting the normal Update -> Status flow.
        manifest_index = next(
            (
                index
                for index in range(self.tabs.count())
                if self.tabs.tabText(index) == "Update-Datei / Manifest"
            ),
            -1,
        )
        advanced_index = next(
            (
                index
                for index in range(self.tabs.count())
                if self.tabs.tabText(index) == "Erweitert"
            ),
            -1,
        )
        if manifest_index >= 0 and advanced_index >= 0 and manifest_index != advanced_index - 1:
            manifest_widget = self.tabs.widget(manifest_index)
            manifest_text = self.tabs.tabText(manifest_index)
            self.tabs.removeTab(manifest_index)
            advanced_index = next(
                (
                    index
                    for index in range(self.tabs.count())
                    if self.tabs.tabText(index) == "Erweitert"
                ),
                self.tabs.count(),
            )
            self.tabs.insertTab(advanced_index, manifest_widget, manifest_text)

        # Status is a secondary action. Put the small button into the protocol
        # toolbar directly left of the two protocol buttons instead of giving it
        # a full-width row inside the firmware page.
        clear_log_button = next(
            (
                button
                for button in self.findChildren(QPushButton)
                if button.text() == "Protokoll leeren"
            ),
            None,
        )
        root_layout = self.centralWidget().layout() if self.centralWidget() else None
        source_layout = self._layout_containing(root_layout, self.ota_reattach_btn)
        log_toolbar = self._layout_containing(root_layout, clear_log_button)
        if source_layout is not None and log_toolbar is not None and clear_log_button is not None:
            source_layout.removeWidget(self.ota_reattach_btn)
            insert_at = log_toolbar.indexOf(clear_log_button)
            log_toolbar.insertWidget(max(0, insert_at), self.ota_reattach_btn)

    # ------------------------------------------------------------------
    # Final maintenance UI: persistent statistics counters
    # ------------------------------------------------------------------
    def _advanced(self):
        widget = super()._advanced()
        layout = widget.layout()

        # Replace the old single-counter presentation, but keep its proven core
        # and controls instantiated underneath for compatibility with the older
        # maintenance layer.  The final product presents the newer multi-counter
        # frontend below instead.
        insert_at = layout.indexOf(self.statistics_current)
        if insert_at < 0:
            insert_at = max(0, layout.count() - 1)

        for label in widget.findChildren(QLabel):
            text = label.text()
            if "Wartung – Mainboard OTA-Vorgänge" in text:
                label.setText("<hr><b>Wartung – Persistente Statistikzähler</b>")
            elif "eigenständigen gemeinsamen" in text and "0x24" in text:
                label.setText(
                    "Der Maintenance-Core prüft den Originalzustand, sichert die vollständige "
                    "128-Byte-Statistikdatei und ändert nur explizit bekannte uint32-Zähler. "
                    "Datei und RAM werden nach dem kontrollierten Neustart von "
                    "<code>phnixIot4G</code> erneut verifiziert. Es werden keine "
                    "RS485-/Modbus-Telegramme gesendet."
                )
            elif text == "Neuer Wert:":
                # Static label from the hidden legacy single-counter row.
                label.setVisible(False)

        for name in (
            "statistics_current",
            "statistics_target",
            "statistics_show_btn",
            "allow_statistics_write",
            "statistics_set_btn",
        ):
            control = getattr(self, name, None)
            if control is not None:
                control.setVisible(False)

        self._statistics_multi_current_values: dict[str, int] = {}
        self._statistics_multi_current_labels: dict[str, QLabel] = {}
        self._statistics_multi_targets: dict[str, QLineEdit] = {}

        grid = QGridLayout()
        grid.addWidget(QLabel("<b>Zähler</b>"), 0, 0)
        grid.addWidget(QLabel("<b>Aktuell</b>"), 0, 1)
        grid.addWidget(QLabel("<b>Neuer Wert</b>"), 0, 2)
        for row, (key, label_text, _flag) in enumerate(STATISTICS_FIELDS, start=1):
            label = QLabel(label_text)
            if key == "power_reset":
                label.setToolTip(
                    "Power-Reset-t wird beim Start von phnixIot4G zunächst nur im RAM erhöht. "
                    "Der Maintenance-Core berücksichtigt diesen Start und stellt danach auch den "
                    "persistenten Dateiwert exakt auf den gewünschten Endwert."
                )
            elif key == "active_reset":
                label.setToolTip(
                    "Active-Reset-t zählt vollständige, von phnixIot4G ausgelöste Modem/Linux-"
                    "Neustarts; ein normaler Prozessneustart erhöht diesen Zähler nicht."
                )
            current = QLabel("–")
            target = QLineEdit()
            target.setPlaceholderText("leer = unverändert")
            target.textChanged.connect(self._buttons)
            grid.addWidget(label, row, 0)
            grid.addWidget(current, row, 1)
            grid.addWidget(target, row, 2)
            self._statistics_multi_current_labels[key] = current
            self._statistics_multi_targets[key] = target
        layout.insertLayout(insert_at, grid)
        insert_at += 1

        self.statistics_multi_show_btn = QPushButton("Aktuelle Statistikwerte prüfen")
        self.statistics_multi_show_btn.clicked.connect(self._statistics_multi_show)
        layout.insertWidget(insert_at, self.statistics_multi_show_btn)
        insert_at += 1

        note = QLabel(
            "<b>Power-Reset-t:</b> Beim notwendigen Dienstneustart erhöht phnixIot4G den "
            "Zähler zunächst im RAM. Der Maintenance-Core verwendet deshalb für den Start intern "
            "den passenden Vorwert und setzt anschließend die persistente Datei auf denselben "
            "gewünschten Endwert. Datei und RAM werden danach gemeinsam verifiziert. Ein Endwert "
            "0 ist bei einem laufenden phnixIot4G nicht möglich. Leer gelassene Felder bleiben "
            "unverändert."
        )
        note.setWordWrap(True)
        layout.insertWidget(insert_at, note)
        insert_at += 1

        self.allow_statistics_multi_write = QCheckBox(
            "Ändern der ausgewählten persistenten Statistikwerte erlauben"
        )
        self.allow_statistics_multi_write.toggled.connect(self._buttons)
        layout.insertWidget(insert_at, self.allow_statistics_multi_write)
        insert_at += 1

        self.statistics_multi_set_btn = QPushButton("Ausgewählte Statistikwerte setzen")
        self.statistics_multi_set_btn.clicked.connect(self._statistics_multi_set)
        layout.insertWidget(insert_at, self.statistics_multi_set_btn)
        return widget

    @staticmethod
    def _statistics_counters_core_path() -> Path:
        return base.backend_dir() / "updater/common/phnix_statistics_counters.py"

    def _statistics_counters_command(self, adb: Path, *args: str) -> list[str]:
        return [
            str(base.backend_python()),
            str(self._statistics_counters_core_path()),
            "--adb",
            str(adb),
            "--output",
            "json",
            *args,
        ]

    def _statistics_multi_updates(self) -> dict[str, int] | None:
        if not hasattr(self, "_statistics_multi_targets"):
            return {}
        updates: dict[str, int] = {}
        for key, _label, _flag in STATISTICS_FIELDS:
            text = self._statistics_multi_targets[key].text().strip()
            if not text:
                continue
            try:
                value = int(text, 10)
            except ValueError:
                return None
            if not 0 <= value <= 0xFFFFFFFF:
                return None
            if key == "power_reset" and value < 1:
                return None
            updates[key] = value
        return updates

    def _statistics_multi_show(self) -> None:
        adb = self._require_adb()
        if not adb:
            return
        core = self._statistics_counters_core_path()
        if not core.is_file():
            QMessageBox.critical(
                self,
                "Maintenance-Core fehlt",
                f"Der Statistik-Maintenance-Core wurde nicht gefunden:\n{core}",
            )
            return
        self._run(
            "statistics-multi-show",
            self._statistics_counters_command(adb, "show"),
            str(base.backend_dir()),
        )

    def _statistics_multi_set(self) -> None:
        if self.busy or not self.allow_statistics_multi_write.isChecked():
            return
        updates = self._statistics_multi_updates()
        if updates is None:
            QMessageBox.warning(
                self,
                "Ungültiger Wert",
                "Alle Werte müssen ganzzahlige uint32-Werte sein. Power-Reset-t muss mindestens 1 sein.",
            )
            return
        if not updates:
            QMessageBox.information(
                self,
                "Keine Änderung ausgewählt",
                "Bitte mindestens einen neuen Statistikwert eintragen. Leer bedeutet unverändert.",
            )
            return
        adb = self._require_adb()
        if not adb:
            return
        core = self._statistics_counters_core_path()
        if not core.is_file():
            QMessageBox.critical(
                self,
                "Maintenance-Core fehlt",
                f"Der Statistik-Maintenance-Core wurde nicht gefunden:\n{core}",
            )
            return

        labels = {key: label for key, label, _flag in STATISTICS_FIELDS}
        changes = []
        for key, value in updates.items():
            old = self._statistics_multi_current_values.get(key)
            old_text = str(old) if isinstance(old, int) else "nicht geprüft"
            changes.append(f"{labels[key]}: {old_text} → {value}")
        if (
            QMessageBox.warning(
                self,
                "Persistente Statistikwerte ändern?",
                "Der Originaldienst wird für wenige Sekunden kontrolliert gestoppt. Vor dem "
                "Schreiben wird die vollständige 128-Byte-Statistikdatei lokal gesichert. "
                "Nur die ausgewählten bekannten Zähler sowie die notwendige Power-Reset-"
                "Kompensation dürfen verändert werden. Datei und RAM werden anschließend "
                "verifiziert.\n\n"
                + "\n".join(changes)
                + "\n\nFortfahren?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return

        args = ["set"]
        flags = {key: flag for key, _label, flag in STATISTICS_FIELDS}
        for key, value in updates.items():
            args += [flags[key], str(value)]
        args += [
            "--execute",
            "--confirm",
            STATISTICS_CONFIRM_TOKEN,
            "--backup-dir",
            str(self._statistics_backup_dir()),
        ]
        self._run(
            "statistics-multi-set",
            self._statistics_counters_command(adb, *args),
            str(base.backend_dir()),
        )

    def _set_statistics_multi_values(self, values: object) -> bool:
        if not isinstance(values, dict):
            return False
        valid = False
        for key, _label, _flag in STATISTICS_FIELDS:
            value = values.get(key)
            if isinstance(value, int):
                self._statistics_multi_current_values[key] = value
                self._statistics_multi_current_labels[key].setText(str(value))
                valid = True
        return valid

    def _done(self, op, code, output):
        if op not in {"statistics-multi-show", "statistics-multi-set"}:
            super()._done(op, code, output)
            return

        # Re-use the inherited process cleanup and logging without sending this
        # independent maintenance result through the OTA result renderer.
        super()._done("handled-result", code, output)

        if op == "statistics-multi-show":
            result = self._last_event(output, "inspect")
            if result and self._set_statistics_multi_values(result.get("values")):
                if code != 0 or result.get("ok") is not True:
                    QMessageBox.warning(
                        self,
                        "Statistikwerte gelesen",
                        "Die Werte konnten gelesen werden, aber mindestens eine Sicherheitsprüfung "
                        "des Maintenance-Cores ist nicht erfüllt. Schreiben bleibt gesperrt, bis "
                        "der Originalzustand wieder eindeutig ist.",
                    )
                self._buttons()
                return
            QMessageBox.warning(
                self,
                "Statistikwerte",
                "Die persistenten Statistikwerte konnten nicht sicher gelesen werden. Details stehen im Protokoll.",
            )
            return

        complete = self._last_event(output, "complete")
        if code == 0 and complete and self._set_statistics_multi_values(complete.get("values")):
            backup = complete.get("backup")
            changed = complete.get("changed") or {}
            labels = {key: label for key, label, _flag in STATISTICS_FIELDS}
            lines = [
                f"{labels[key]}: {self._statistics_multi_current_values.get(key)}"
                for key in changed
                if key in labels
            ]
            for target in self._statistics_multi_targets.values():
                target.clear()
            self.allow_statistics_multi_write.setChecked(False)
            QMessageBox.information(
                self,
                "Statistikwerte geändert",
                "Die ausgewählten Werte wurden erfolgreich geändert.\n\n"
                + "\n".join(lines)
                + "\n\nPersistente Datei: verifiziert\nRAM nach Neustart: verifiziert\n"
                + f"Backup: {backup or 'siehe Protokoll'}",
            )
            if not self._modem_info_running:
                self._refresh_modem_info()
            return

        error = self._last_event(output, "error")
        message = (
            str(error.get("message"))
            if isinstance(error, dict) and error.get("message")
            else "Der Statistik-Maintenance-Core hat den Vorgang nicht erfolgreich abgeschlossen."
        )
        QMessageBox.critical(
            self,
            "Wartung fehlgeschlagen",
            message + "\n\nDetails stehen im Protokoll.",
        )

    def _modem_info_result(self, value: object):
        super()._modem_info_result(value)
        if not isinstance(value, PhnixModemInfo) or not hasattr(self, "_statistics_multi_current_labels"):
            return
        stats = value.statistics
        values = {
            "dtu_ota": stats.dtu_ota_count,
            "mainboard_ota": stats.mainboard_ota_count,
            "power_reset": stats.power_reset_count,
            "active_reset": stats.active_reset_count,
        }
        self._set_statistics_multi_values(values)

    def _buttons(self):
        super()._buttons()
        if not hasattr(self, "statistics_multi_show_btn"):
            return
        enabled = not self.busy and self._adb_ready()
        self.statistics_multi_show_btn.setEnabled(enabled)
        self.allow_statistics_multi_write.setEnabled(not self.busy)
        for target in self._statistics_multi_targets.values():
            target.setEnabled(not self.busy)
        updates = self._statistics_multi_updates()
        self.statistics_multi_set_btn.setEnabled(
            enabled
            and self.allow_statistics_multi_write.isChecked()
            and updates is not None
            and bool(updates)
        )

    def _set_step(self, key: str, level: str, text: str):
        """Collapse presentation aliases onto the existing runner flow row."""
        return super()._set_step(self.FLOW_KEY_ALIASES.get(key, key), level, text)

    def _render_runner_status(self, status: dict) -> None:
        """Apply final product-only presentation cleanup after runner rendering."""
        super()._render_runner_status(status)

        phase = str(status.get("phase") or "")
        if phase == "dry-run-complete" and not self._runner_autostart_after_prepare:
            # The completed preflight is already fully represented in the flow
            # box. Do not repeat the same state directly below it as a large
            # progress caption/source line when no transfer exists yet.
            self._flow_title = "Vorprüfung erfolgreich"
            self.progress_text.clear()
            if hasattr(self, "progress_sources"):
                self.progress_sources.clear()
            self._render_flow()

        if (
            status.get("service_restart_requested") is True
            and status.get("service_restart_verified") is True
        ):
            self._set_step(
                "runner-service-restart",
                "ok",
                "LTE-Kommunikationsdienst wurde kontrolliert neu gestartet.",
            )

    def _update_debug_line(self, line: str, event: object) -> None:
        """Accept live serial transfer progress for autonomous runner updates.

        The inherited diagnostics layer only accepts serial progress after the
        legacy controller created a ``phase-c5a8`` row. Autonomous runner runs
        use ``runner-c5a8`` instead, so otherwise the LTE log is written but the
        visible serial percentage never updates.
        """
        super()._update_debug_line(line, event)
        if (
            getattr(event, "kind", None) == "transfer-progress"
            and self._runner_run_id
            and not self._runner_terminal
        ):
            # A live transfer-progress event itself is sufficient evidence for
            # the presentation layer that a percentage is meaningful. This also
            # prevents a runner poll that is a fraction behind from resetting
            # the freshly received serial percentage back to an empty bar.
            self._runner_transfer_visible = True
            self._phnix_transfer_event = event
            self._serial_progress_seen_at = time.monotonic()
            self._render_transfer_progress()

    def _debug_status(self, status: str, error: object) -> None:
        super()._debug_status(status, error)
        if status in {"Getrennt", "Verbindung beendet", "Verbindung fehlgeschlagen"}:
            self._serial_progress_seen_at = None

    def _expire_stale_serial_progress(self) -> None:
        """Fall back to runner progress if a connected serial stream goes stale."""
        if (
            self._phnix_transfer_event is None
            or self._serial_progress_seen_at is None
            or self._runner_terminal
        ):
            return
        if time.monotonic() - self._serial_progress_seen_at < self.SERIAL_PROGRESS_STALE_SECONDS:
            return
        self._phnix_transfer_event = None
        self._serial_progress_seen_at = None
        if self._runner_transfer_visible:
            self._render_transfer_progress()


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
