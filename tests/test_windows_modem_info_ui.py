import unittest
from pathlib import Path


class WindowsModemInfoUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.desktop = Path("updater/windows/foxair_updater_desktop.py").read_text(
            encoding="utf-8"
        )
        cls.lte_ui = Path("updater/windows/foxair_updater_lte_diagnostics.py").read_text(
            encoding="utf-8"
        )
        cls.operator_ui = Path(
            "updater/windows/foxair_updater_operator_display.py"
        ).read_text(encoding="utf-8")
        cls.maintenance_ui = Path(
            "updater/windows/foxair_updater_maintenance.py"
        ).read_text(encoding="utf-8")
        cls.product_ui = Path(
            "updater/windows/foxair_updater_runner_product.py"
        ).read_text(encoding="utf-8")
        cls.operators = Path("updater/common/network_operators.py").read_text(
            encoding="utf-8"
        )
        cls.modem = Path("updater/common/phnix_modem_info.py").read_text(
            encoding="utf-8"
        )
        cls.maintenance = Path(
            "updater/common/phnix_statistics_maintenance.py"
        ).read_text(encoding="utf-8")
        cls.transport = Path("updater/common/adb_transport.py").read_text(
            encoding="utf-8"
        )
        cls.base_ui = Path("updater/windows/foxair_updater_gui.py").read_text(
            encoding="utf-8"
        )
        cls.app_ui = Path("updater/windows/foxair_updater_app.py").read_text(encoding="utf-8")
        cls.traffic_ui = Path(
            "updater/windows/foxair_updater_traffic.py"
        ).read_text(encoding="utf-8")
        cls.build = Path("updater/windows/build_windows_portable.bat").read_text(
            encoding="utf-8"
        )

    def test_windows_build_uses_product_entrypoint_and_maintenance_backend(self):
        self.assertIn(
            "updater\\windows\\foxair_updater_runner_product.py", self.build
        )
        self.assertIn(
            "backend\\updater\\common\\phnix_statistics_maintenance.py",
            self.build,
        )
        self.assertIn("phnix_statistics_counters.py", self.product_ui)

    def test_modem_info_is_read_only_process_memory_diagnostics(self):
        self.assertIn('"Modem Info / LTE Diagnose"', self.desktop)
        self.assertIn("read_phnix_modem_info", self.lte_ui)
        self.assertIn("dd if=/proc/{pid}/mem", self.modem)
        self.assertIn("| od -An -v -tx1", self.modem)
        self.assertNotIn("/dev/ttyHSL2", self.modem)
        self.assertNotIn("FC03", self.modem)
        self.assertNotIn("of=/proc/", self.modem)

    def test_windows_adb_processes_do_not_flash_console_windows(self):
        self.assertIn("CREATE_NO_WINDOW", self.transport)
        self.assertIn("creationflags=self._creationflags()", self.transport)

    def test_main_window_is_wider_and_traffic_actions_reach_program_log(self):
        self.assertIn("self.resize(1100, 780)", self.base_ui)
        self.assertIn('self._log("[Modem Diagnose / Traffic] "', self.traffic_ui)
        self.assertIn("Diagnose ist aktiv und passiv angehängt", self.traffic_ui)
        self.assertIn("Aktualisierung abgeschlossen", self.traffic_ui)
        self.assertIn('self._log("[Modem Diagnose / Traffic] Fehler: "', self.traffic_ui)

    def test_live_confirmed_lte_addresses_are_encoded(self):
        expected = [
            "ERROR_STATUS_ADDRESS = 0x93124",
            "STATISTICS_ADDRESS = 0x91B60",
            "BOARD_SOFTWARE_CODE_ADDRESS = 0x935E1",
            "ICCID_ADDRESS = 0x9365C",
            "IMSI_ADDRESS = 0x93674",
            "IMEI_ADDRESS = 0x93688",
            "PCLIENT_POINTER_ADDRESS = 0x94EB4",
            "ROAMING_VALID_ADDRESS = 0x97FE8",
            "CURRENT_PLMN_VALID_ADDRESS = 0x98020",
            "LAC_ADDRESS = 0x98168",
            "CELL_ID_ADDRESS = 0x9816C",
            "SERVING_SYSTEM_ADDRESS = 0x981B4",
            "MODE_TYPE_ADDRESS = 0x98912",
            "DEVICE_SECRET_ADDRESS = 0x9896C",
            "PRODUCT_SECRET_ADDRESS = 0x989B0",
            "DEVICE_NAME_ADDRESS = 0x98A58",
            "PRODUCT_KEY_ADDRESS = 0x98A98",
            "SIM_STATUS_ADDRESS = 0x98AB0",
        ]
        for text in expected:
            self.assertIn(text, self.modem)

    def test_ui_has_requested_sections_and_secret_masking(self):
        for heading in (
            "<h3>Mainboard</h3>",
            "<h3>Modem</h3>",
            "<h3>SIM</h3>",
            "<h3>Mobilfunk</h3>",
            "<h3>Netzwerk</h3>",
            "<h3>Cloud</h3>",
            "<h3>Statistik / Fehler</h3>",
        ):
            self.assertIn(heading, self.lte_ui)
        self.assertIn('QCheckBox("Cloud-Secrets anzeigen")', self.lte_ui)
        self.assertIn("••••••••••••••••", self.lte_ui)
        self.assertIn("Mobilfunk-IP / PDP-IP", self.lte_ui)
        self.assertIn("MQTT / Cloud", self.lte_ui)

    def test_operator_ui_shows_current_and_home_network(self):
        self.assertIn("Aktueller Netzbetreiber", self.operator_ui)
        self.assertIn("Heimatnetz (aus IMSI)", self.operator_ui)
        self.assertIn("Netzbeschreibung (Modem)", self.operator_ui)
        self.assertIn('(262, 1): "Telekom Deutschland GmbH"', self.operators)
        self.assertIn('(208, 1): "Orange France"', self.operators)

    def test_mainboard_ota_counter_is_presented_as_operations_with_tooltip(self):
        self.assertIn("Mainboard OTA-Vorgänge", self.operator_ui)
        self.assertIn("Vom LTE-Modul gezählte OTA-Aufträge", self.operator_ui)
        self.assertIn('href="ota-counter"', self.operator_ui)
        self.assertIn("linkHovered", self.operator_ui)

    def test_statistics_write_ui_is_only_a_frontend_for_shared_core(self):
        self.assertIn(
            "import foxair_updater_operator_display as operator", self.maintenance_ui
        )
        self.assertIn(
            '"phnix_statistics_maintenance.py"', self.maintenance_ui
        )
        self.assertIn(
            '"set-mainboard-ota-count"', self.maintenance_ui
        )
        self.assertIn(
            '"PHNIX-STATISTICS-WRITE"', self.maintenance_ui
        )
        self.assertIn(
            "Ändern des persistenten Statistikzustands erlauben",
            self.maintenance_ui,
        )
        self.assertNotIn("kill -TERM", self.maintenance_ui)
        self.assertNotIn("kill -STOP", self.maintenance_ui)
        self.assertNotIn("REMOTE_STATISTICS", self.maintenance_ui)
        self.assertIn("kill -TERM", self.maintenance)
        self.assertIn("kill -STOP", self.maintenance)

    def test_unverified_ascii_candidate_is_not_presented_as_confirmed_id(self):
        self.assertIn("unverified_device_id_candidate", self.modem)
        self.assertNotIn("Device-/DTU-ID:", self.lte_ui)

    def test_advanced_block_reset_uses_safe_controller_restore(self):
        self.assertIn(
            'QCheckBox("Blockzustand zurücksetzen erlauben")', self.desktop
        )
        self.assertIn('"cache.pending"', self.desktop)
        self.assertNotIn("marker.unlink()", self.desktop)
        self.assertIn("dirty_state_reset_is_safe", self.desktop)
        self.assertIn('self._backend("restore"', self.desktop)

    def test_dry_run_dirty_state_bypasses_advanced_opt_in_only_for_popup(self):
        self.assertIn("def _reset_block_pending(self, checked: bool = False, *, from_dry_run: bool = False)", self.desktop)
        self.assertIn("self._reset_block_pending(from_dry_run=True)", self.desktop)
        self.assertIn("not from_dry_run and not self.allow_block_reset.isChecked()", self.desktop)

    def test_lte_log_contains_translations_and_events_only_refine_existing_steps(self):
        self.assertIn('explained = explain_debug_line(line).splitlines()', self.lte_ui)
        self.assertIn('strftime("%H:%M:%S.%f")[:-3]', self.lte_ui)
        self.assertIn("if key in self._flow_steps:", self.lte_ui)
        for kind in ("transfer-complete", "manufacturer-success", "mqtt-normal"):
            self.assertIn(f'kind == "{kind}"', self.lte_ui)
        self.assertNotIn('kind == "cloud-progress"', self.lte_ui)
        self.assertIn(
            'capture.add_status_consumer("log", self._debug_log_status, notify_initial=False)',
            self.lte_ui,
        )

    def test_debug_monitor_controls_status_and_update_page_entry(self):
        self.assertIn('self.mode.setCurrentIndex(1)', self.lte_ui)
        self.assertIn('QPushButton("Verbinden")', self.lte_ui)
        self.assertIn('QPushButton("Trennen")', self.lte_ui)
        for status in ("Verbinde …", "Verbunden", "Getrennt", "Verbindung fehlgeschlagen"):
            self.assertIn(status, self.lte_ui + Path("updater/common/phnix_debug.py").read_text(encoding="utf-8"))
        log_row = self.base_ui.split('clear_button = QPushButton("Protokoll leeren")', 1)[1].split(
            "layout.addLayout(row)", 1
        )[0]
        self.assertNotIn('QPushButton("LTE-Modem-Log öffnen")', log_row)
        self.assertIn('save_button = QPushButton("Protokoll speichern…")', log_row)
        self.assertIn('QPushButton("PHNIX Debugmonitor öffnen")', self.lte_ui)
        self.assertNotIn('QPushButton("LTE-Modem-Log öffnen")', self.app_ui)
        self.assertIn('setFixedHeight(20)', self.base_ui)
        self.assertIn('self.progress.setTextVisible(False)', self.base_ui)
        self.assertIn('QProgressBar::chunk', self.base_ui)
        self.assertIn('background: palette(highlight)', self.base_ui)
        self.assertNotIn('setMinimumHeight(54)', self.base_ui + self.app_ui)
        update_page = self.base_ui.split("def _update(self):", 1)[1].split("def _status", 1)[0]
        self.assertNotIn("Manifest", update_page)
        self.assertIn("Update-Datei", update_page)

    def test_debug_monitor_is_unowned_and_closed_with_main_window(self):
        self.assertIn("PhnixDebugWindow()", self.lte_ui)
        self.assertNotIn("PhnixDebugWindow(self)", self.lte_ui)
        close_event = self.lte_ui.split("def closeEvent(self, event):", 2)[2]
        self.assertIn("self._debug_window.close()", close_event)
        self.assertNotIn("WindowStaysOnTopHint", self.lte_ui)

    def test_update_howto_link_is_available(self):
        self.assertIn('QPushButton("Update-Anleitung")', self.base_ui)
        self.assertIn(
            "https://github.com/dosordie/FoxAir_updater/blob/main/docs/HowTo/firmware_update_windows.md",
            self.base_ui,
        )

    def test_transfer_progress_has_separate_percent_and_friendly_sources(self):
        render = self.lte_ui.split("def _render_transfer_progress", 1)[1].split(
            "def _update_existing_debug_step", 1
        )[0]
        self.assertIn('self.progress_percent_label.setText(f"{percent:.1f} %")', render)
        self.assertIn('self.progress_percent_label.setText(f"{percent} %")', render)
        self.assertNotIn("setFormat", render)
        self.assertIn("PHNIX Originaldienst:", render)
        self.assertIn("Windows Updater:", render)
        self.assertNotIn("Controller:", render)
        self.assertIn("self.progress_percent_label = QLabel", self.operator_ui)
        self.assertIn("self.progress.valueChanged.connect", self.operator_ui)
        self.assertIn(
            "self.progress_percent_label.setFont(self.ota_elapsed_label.font())",
            self.operator_ui,
        )

    def test_monitoring_recovered_marks_recovery_step_ok(self):
        recovered = self.app_ui.split('elif event == "monitoring-recovered":', 1)[1].split(
            'elif event == "monitoring-connection-lost":', 1
        )[0]
        self.assertIn('"monitoring-recovery", "ok"', recovered)
        self.assertIn("ADB-Verbindung wiederhergestellt", recovered)
        self.assertNotIn('"complete"', recovered)

    def test_automatic_update_logs_prefer_logs_directory_with_warning_fallback(self):
        log_setup = self.lte_ui.split("def _start_automatic_logs", 1)[1].split(
            "def _finish_automatic_logs", 1
        )[0]
        self.assertIn('directory = firmware_directory / "Logs"', log_setup)
        self.assertIn("directory.mkdir(exist_ok=True)", log_setup)
        self.assertEqual(log_setup.count('f"FoxAir_Update_{stamp}'), 4)
        self.assertIn("Ordner „Logs“ konnte nicht verwendet werden", log_setup)
        self.assertIn("direkt im Firmware-Verzeichnis gespeichert", log_setup)
        self.assertIn("except OSError as fallback_error", log_setup)
        self.assertIn("capture = self._ensure_debug_capture(for_update=True)", log_setup)

    def test_visible_windows_safety_name_is_update_protection(self):
        visible_sources = self.app_ui + self.desktop + self.lte_ui
        wrapper_output = Path(
            "updater/windows/phnix_windows_controller_wrapper.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Windows-Sicherheitswrapper", visible_sources + wrapper_output)
        self.assertIn("Update-Schutz", visible_sources)
        self.assertIn("Update-Schutz", wrapper_output)
        self.assertIn("phnix_windows_controller_wrapper", self.desktop)
        self.assertIn("windows_wrapper", self.desktop)

    def test_terminal_log_cleanup_precedes_modal_base_done(self):
        done = self.lte_ui.split("def _done(self, op, code, output):", 1)[1].split(
            "def _log", 1
        )[0]
        cleanup = done.index("self._finish_automatic_logs()")
        modal_base_done = done.index("super()._done(op, code, output)")
        self.assertLess(cleanup, modal_base_done)
        self.assertIn('op in {"dry", "update"}', done)
        self.assertIn("keep_serial_tail", done)
        self.assertIn("SERIAL_FALLBACK_TAIL_MS", done)

    def test_serial_completion_is_run_bound_and_reuses_reattach(self):
        self.assertIn("self._update_run_generation += 1", self.lte_ui)
        self.assertIn("SerialCompletionSequence(generation)", self.lte_ui)
        self.assertIn("run=generation", self.lte_ui)
        self.assertIn("generation != self._update_run_generation", self.lte_ui)
        self.assertIn("self._serial_c5a8_started", self.lte_ui)
        self.assertIn("self._serial_transfer_started", self.lte_ui)
        self.assertIn("self._serial_monitoring_lost", self.lte_ui)
        self.assertIn("self._debug_capture.identity == self._serial_capture_identity", self.lte_ui)
        self.assertIn("self._reattach_ota()", self.lte_ui)
        self.assertIn("QTimer.singleShot(3000", self.lte_ui)
        self.assertNotIn("remove_consumer(\"window\")", self.lte_ui.split(
            "def _finish_automatic_logs", 1
        )[1].split("def _debug_log_status", 1)[0])

    def test_elapsed_timer_stops_for_all_terminal_success_paths(self):
        self.assertIn('if phase == "success":', self.operator_ui)
        self.assertIn('hook.get("phase") == "success"', self.operator_ui)
        self.assertIn('hook.get("terminal") is True', self.operator_ui)
        serial_success = self.lte_ui.split("def _confirm_serial_completion", 1)[1].split(
            "def _serial_reattach", 1
        )[0]
        self.assertIn("self._stop_ota_elapsed()", serial_success)

    def test_serial_success_is_not_downgraded_when_reattach_fails(self):
        reattach_result = self.lte_ui.split('if op == "ota-reattach"', 1)[1].split(
            "def _log", 1
        )[0]
        self.assertIn("Firmwareupdate erfolgreich – ADB weiterhin nicht erreichbar.", reattach_result)
        self.assertIn("ADB-Abschlusskontrolle derzeit nicht möglich", reattach_result)
        self.assertIn('self._set_step("adb-reattach", "warn", recovery_note)', reattach_result)
        self.assertIn('self._log("[Hinweis] " + recovery_note)', reattach_result)
        self.assertIn("QMessageBox.warning(", reattach_result)
        self.assertIn("recovery_note,", reattach_result)
        self.assertNotIn("Firmwareupdate fehlgeschlagen", reattach_result)

    def test_serial_success_finishes_only_local_wrapper_marker(self):
        confirm = self.lte_ui.split("def _confirm_serial_completion", 1)[1].split(
            "def _serial_reattach", 1
        )[0]
        self.assertIn("desktop.windows_wrapper.clear_cache_pending()", confirm)
        self.assertNotIn("restore_update_cache", confirm)
        self.assertNotIn("REMOTE_", confirm)

    def test_reattach_requires_terminal_success_status(self):
        result = self.lte_ui.split('if op == "ota-reattach"', 1)[1].split(
            "def _log", 1
        )[0]
        self.assertIn('hook.get("phase") == "success"', result)
        self.assertIn('hook.get("terminal") is True', result)
        self.assertIn("Abschlusskontrolle noch nicht terminal bestätigt", result)
        self.assertIn("ADB wieder verbunden – Abschlusskontrolle läuft.", result)
        pending = result.split("elif code == 0 and status is not None:", 1)[1].split("else:", 1)[0]
        self.assertNotIn("QMessageBox", pending)
        self.assertIn("self.ota_reattach_btn.setVisible(True)", result)

    def test_monitoring_loss_confirms_already_complete_current_sequence(self):
        handler = self.lte_ui.split("def _handle_record", 1)[1].split(
            "def _start_automatic_logs", 1
        )[0]
        self.assertIn("self._serial_sequence.complete", handler)
        self.assertIn("self._confirm_serial_completion(self._update_run_generation)", handler)

    def test_manufacturer_success_after_monitoring_loss_has_no_controller_check_text(self):
        apply_event = self.lte_ui.split("def _apply_debug_event", 1)[1].split(
            "def _handle_record", 1
        )[0]
        self.assertIn("if self._serial_monitoring_lost", apply_event)
        self.assertIn("vollständige Abschlusssequenz wird noch geprüft", apply_event)

    def test_serial_success_controller_exit_uses_only_generic_cleanup(self):
        done = self.lte_ui.split("def _done(self, op, code, output):", 1)[1].split(
            "def _log", 1
        )[0]
        serial_exit = done.split('if op == "update" and self._serial_fallback_success:', 1)[1].split(
            'if op == "update" and self._has_event(', 1
        )[0]
        self.assertIn('super()._done("handled-result", code, output)', serial_exit)
        self.assertIn("return", serial_exit)
        self.assertNotIn("_reattach_ota", serial_exit)
        self.assertNotIn("QMessageBox", serial_exit)
        normal_path = done.split('if op == "update" and self._serial_fallback_success:', 1)[0]
        self.assertIn("keep_serial_tail", normal_path)
        self.assertIn("self._serial_monitoring_lost", normal_path)

    def test_serial_reattach_waits_for_busy_update_cleanup_and_starts_once(self):
        confirm = self.lte_ui.split("def _confirm_serial_completion", 1)[1].split(
            "def _render_transfer_progress", 1
        )[0]
        reattach = confirm.split("def _serial_reattach", 1)[1]
        self.assertIn("self._serial_reattach_pending_generation = generation", confirm)
        self.assertIn("or self.busy", reattach)
        self.assertIn("self._serial_reattach_started_generation == generation", reattach)
        self.assertIn("self._serial_reattach_pending_generation = None", reattach)
        self.assertIn("self._reattach_ota()", reattach)
        self.assertIn("def _automatic_monitoring_reattach", self.app_ui)
        automatic = self.lte_ui.split("def _automatic_monitoring_reattach", 1)[1].split(
            "def _render_transfer_progress", 1
        )[0]
        self.assertIn("self._serial_reattach(self._update_run_generation)", automatic)

        done = self.lte_ui.split("def _done(self, op, code, output):", 1)[1].split(
            "def _log", 1
        )[0]
        serial_exit = done.split('if op == "update" and self._serial_fallback_success:', 1)[1].split(
            "return", 1
        )[0]
        self.assertLess(
            serial_exit.index('super()._done("handled-result", code, output)'),
            serial_exit.index("self._serial_reattach(generation)"),
        )

    def test_early_serial_success_keeps_only_short_lte_tail(self):
        done = self.lte_ui.split("def _done(self, op, code, output):", 1)[1].split(
            "def _log", 1
        )[0]
        self.assertIn("keep_success_tail", done)
        self.assertIn("self._serial_success_tail_generation == generation", done)
        self.assertIn("if keep_success_tail or keep_serial_tail:", done)
        self.assertIn("self._automatic_log.close()", done)
        timeout_block = done.split("if keep_serial_tail:", 1)[1].split("else:", 1)[0]
        self.assertIn("SERIAL_FALLBACK_TAIL_MS", timeout_block)
        self.assertNotIn("QTimer.singleShot(600000", done.split("keep_success_tail =", 1)[0])
        finish = self.lte_ui.split("def _finish_automatic_logs", 1)[1].split(
            "def _debug_log_status", 1
        )[0]
        self.assertNotIn('remove_consumer("window")', finish)

    def test_debug_disconnect_fallback_and_source_timestamp_reset(self):
        self.assertIn(
            '"Monitor getrennt – LTE-Logging für laufendes Update weiterhin verbunden."',
            self.lte_ui,
        )
        self.assertIn('self._debug_capture.has_consumer("update")', self.lte_ui)
        status_handler = self.lte_ui.split("def _debug_status", 1)[1].split(
            "def _update_debug_line", 1
        )[0]
        self.assertIn('self._phnix_transfer_event = None', status_handler)
        self.assertIn('self._render_transfer_progress()', status_handler)
        self.assertIn('"Verbindung beendet"', status_handler)
        self.assertIn('"Verbindung fehlgeschlagen"', status_handler)
        ensure_capture = self.lte_ui.split("def _ensure_debug_capture", 1)[1].split(
            "def _attach_monitor_consumer", 1
        )[0]
        self.assertIn('self._debug_last_data = None', ensure_capture)
        self.assertIn('self._debug_connected_since = None', ensure_capture)

    def test_async_update_debug_open_failure_warns_once_in_gui_status_handler(self):
        status_handler = self.lte_ui.split("def _debug_status", 1)[1].split(
            "def _update_debug_line", 1
        )[0]
        self.assertIn('status == "Verbindung fehlgeschlagen"', status_handler)
        self.assertIn('capture.has_consumer("update")', status_handler)
        self.assertIn("not self._debug_open_warning_shown", status_handler)
        self.assertEqual(status_handler.count('self._log("[Warnung] " + warning)'), 1)
        start_logs = self.lte_ui.split("def _start_automatic_logs", 1)[1].split(
            "def _update_debug_line_for_run", 1
        )[0]
        self.assertIn("self._debug_open_warning_shown = False", start_logs)
        self.assertNotIn("if not capture.add_consumer", start_logs)

    def test_completed_flow_phases_are_resolved_to_green(self):
        self.assertIn('self._set_step(key, "ok", text)', self.desktop)
        self.assertIn('self._resolve_flow_step("phase-yield"', self.desktop)
        self.assertIn('self._resolve_flow_step("phase-c350"', self.desktop)
        self.assertIn('self._resolve_flow_step("phase-c5a8"', self.desktop)


if __name__ == "__main__":
    unittest.main()
