import time
import unittest
from pathlib import Path

from updater.common.phnix_debug import DebugEvent, PhnixDebugCapture, SerialCompletionSequence
from updater.common.phnix_service_restart import wait_for_phnix_runtime_ready


ROOT = Path(__file__).resolve().parents[1]


class _GoneSource:
    description = "COM17"

    def read(self, _size):
        raise OSError("COM17 disappeared")

    def close(self):
        pass


class _ReplacementSource:
    description = "COM12"

    def __init__(self):
        self.sent = False

    def read(self, _size):
        if not self.sent:
            self.sent = True
            return b"reconnected\n"
        time.sleep(0.01)
        return b""

    def close(self):
        pass


class WindowsOtaResilienceTests(unittest.TestCase):
    def test_progress_headline_wraps_without_forcing_window_width(self):
        gui = (ROOT / "updater/windows/foxair_updater_gui.py").read_text(encoding="utf-8")
        update_ui = gui.split("self.progress_text = QLabel", 1)[1].split(
            "self.progress = QProgressBar", 1
        )[0]
        self.assertIn("self.progress_text.setWordWrap(True)", update_ui)
        self.assertIn("self.progress_text.setMinimumWidth(0)", update_ui)

    def test_detached_and_serial_reattach_headlines_stay_compact(self):
        lte = (ROOT / "updater/windows/foxair_updater_lte_diagnostics.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ADB-Verbindung unterbrochen – passive Überwachung aktiv.", lte)
        self.assertIn("Firmwareupdate erfolgreich – ADB weiterhin nicht erreichbar.", lte)
        self.assertIn("ADB wieder verbunden – Abschlusskontrolle läuft.", lte)
        self.assertIn("recovery_note = (", lte)
        self.assertIn("Remote-Aufräumarbeiten werden beim nächsten", lte)
        self.assertIn('self._set_step("adb-reattach", "warn", recovery_note)', lte)
        self.assertIn('self._log("[Hinweis] " + recovery_note)', lte)

    def test_detached_fallback_still_requires_complete_strict_sequence(self):
        sequence = SerialCompletionSequence(9)
        events = (
            DebugEvent("transfer-complete"),
            DebugEvent("manufacturer-success"),
            DebugEvent("cloud-progress", progress=100, code="0053"),
            DebugEvent("manufacturer-finished"),
        )
        for event in events[:-1]:
            self.assertFalse(sequence.observe(event, 9))
        self.assertFalse(sequence.complete)
        self.assertTrue(sequence.observe(events[-1], 9))
        self.assertTrue(sequence.complete)

    def test_runtime_readiness_waits_for_delayed_mqtt(self):
        class Adb:
            mqtt_polls = 0

            def shell(self, command, check=True):
                if command == "pidof phnixIot4G":
                    return "2002"
                self.mqtt_polls += 1
                return "tcp ... ESTABLISHED" if self.mqtt_polls == 3 else ""

        adb = Adb()
        self.assertEqual(
            wait_for_phnix_runtime_ready(adb, timeout=0.1, poll_interval=0.001), "2002"
        )
        self.assertEqual(adb.mqtt_polls, 3)

    def test_runtime_readiness_times_out_without_mqtt(self):
        class Adb:
            def shell(self, command, check=True):
                return "2002" if command == "pidof phnixIot4G" else ""

        with self.assertRaisesRegex(RuntimeError, "MQTT-Verbindung"):
            wait_for_phnix_runtime_ready(Adb(), timeout=0.005, poll_interval=0.001)

    def test_mi04_reconnect_keeps_update_sequence_instance(self):
        sources = iter((_GoneSource(), _ReplacementSource()))
        capture = PhnixDebugCapture(lambda: next(sources), "local:MI_04", reconnect_interval=0.01)
        sequence = SerialCompletionSequence(4)
        received = []
        capture.add_consumer("update", lambda line, _event: received.append(line))
        deadline = time.monotonic() + 1
        while not received and time.monotonic() < deadline:
            time.sleep(0.01)
        capture.remove_consumer("update")
        self.assertEqual(received, ["reconnected"])
        self.assertEqual(sequence.generation, 4)

    def test_pre_update_restart_default_and_abort_path_are_wired(self):
        app = (ROOT / "updater/windows/foxair_updater_app.py").read_text(encoding="utf-8")
        lte = (ROOT / "updater/windows/foxair_updater_lte_diagnostics.py").read_text(encoding="utf-8")
        self.assertIn('settings.value("restart_before_update", "true")', app)
        self.assertIn('settings.setValue("restart_before_update"', app)
        self.assertIn("if self.restart_before_update.isChecked():", lte)
        self.assertIn("restart_phnix_iot_service(", lte)
        self.assertIn("threading.Thread(", lte)
        self.assertIn("wait_for_phnix_runtime_ready(client)", lte)
        self.assertIn('"monitoring-recovered-passive",', lte)
        self.assertIn('"monitoring-detached-passive",', lte)
        self.assertIn("Das Firmwareupdate wurde nicht gestartet", lte)
        self.assertLess(lte.index("self._start_automatic_logs(manifest)"), lte.index("restart_phnix_iot_service("))

    def test_pre_update_restart_has_visible_running_success_and_error_steps(self):
        lte = (ROOT / "updater/windows/foxair_updater_lte_diagnostics.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"pre-update-restart", "warn"', lte)
        self.assertIn('"pre-update-restart", "ok"', lte)
        self.assertIn('"pre-update-restart", "error"', lte)
        self.assertIn("PHNIX-LTE-Dienst erfolgreich neu gestartet und betriebsbereit", lte)
        failure = lte.split("def _pre_update_restart_finished", 1)[1].split("def _done", 1)[0]
        self.assertLess(failure.index('"pre-update-restart", "error"'), failure.index("return"))
        self.assertLess(failure.index('"pre-update-restart", "ok"'), failure.index("super()._run"))

    def test_detached_ota_guard_disables_only_new_update_actions(self):
        gui = (ROOT / "updater/windows/foxair_updater_gui.py").read_text(encoding="utf-8")
        lte = (ROOT / "updater/windows/foxair_updater_lte_diagnostics.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("self._ota_serial_guard_active = True", lte)
        self.assertIn('record.get("event") == "monitoring-detached-passive"', lte)
        self.assertIn('record.get("original_service_authoritative") is True', lte)
        self.assertIn('not getattr(self, "_ota_serial_guard_active", False)', gui)
        button_block = gui.split("def _buttons(self):", 1)[1].split("def _log", 1)[0]
        self.assertIn("self.dry.setEnabled(update_start_allowed", button_block)
        self.assertIn("self.update_btn.setEnabled(", button_block)
        self.assertNotIn("update_start_allowed", button_block.split("self.status_btn.setEnabled", 1)[0])

    def test_guard_tracks_only_parsed_ota_activity_and_keeps_full_window(self):
        lte = (ROOT / "updater/windows/foxair_updater_lte_diagnostics.py").read_text(
            encoding="utf-8"
        )
        handler = lte.split("def _update_debug_line", 1)[1].split(
            "def _serial_fallback_allowed", 1
        )[0]
        for kind in (
            "transfer-progress", "transfer-complete", "manufacturer-success",
            "cloud-progress", "manufacturer-finished",
        ):
            self.assertIn(f'"{kind}"', handler)
        self.assertNotIn('"mqtt-normal"', handler.split("_ota_serial_last_activity_at", 1)[0])
        expiry = lte.split("def _expire_ota_serial_guard", 1)[1].split(
            "def _serial_reattach", 1
        )[0]
        self.assertIn("SERIAL_FALLBACK_TAIL_MS", expiry)
        self.assertIn("self._ota_serial_last_activity_at", expiry)
        self.assertIn("QTimer.singleShot(remaining_ms", expiry)

    def test_guard_clears_on_serial_or_reattached_terminal_success(self):
        lte = (ROOT / "updater/windows/foxair_updater_lte_diagnostics.py").read_text(
            encoding="utf-8"
        )
        confirm = lte.split("def _confirm_serial_completion", 1)[1].split(
            "def _activate_ota_serial_guard", 1
        )[0]
        self.assertIn("self._clear_ota_serial_guard(generation, confirmed=True)", confirm)
        reattach = lte.split('if op == "ota-reattach" and self._ota_serial_guard_active:', 1)[1]
        self.assertIn('hook.get("phase") == "success"', reattach)
        self.assertIn('hook.get("terminal") is True', reattach)
        self.assertIn("self._clear_ota_serial_guard(generation, confirmed=True)", reattach)

    def test_firmware_warning_is_version_independent_about_source(self):
        gui = (ROOT / "updater/windows/foxair_updater_gui.py").read_text(encoding="utf-8")
        dialog = gui.split('"Firmwareupdate starten",', 1)[1].split(
            "QMessageBox.Yes | QMessageBox.No", 1
        )[0]
        self.assertNotIn("V3.3", dialog)
        self.assertIn("auf eigenes", dialog)
        self.assertIn("Andere Firmwareziele oder Hardwarevarianten", dialog)

    def test_detached_fallback_tail_and_user_help_cover_full_ota_window(self):
        lte = (ROOT / "updater/windows/foxair_updater_lte_diagnostics.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("SERIAL_FALLBACK_TAIL_MS = 40 * 60 * 1000", lte)
        self.assertIn("SERIAL_FALLBACK_TAIL_MS,", lte)
        detached = lte.split('"monitoring-detached-passive"', 1)[-1]
        self.assertIn("Keine Panik", detached)
        self.assertIn("bis zu etwa 40 Minuten", detached)
        self.assertIn("Keinen Power-Reset", detached)

    def test_permanent_adb_detach_exits_before_another_remote_probe(self):
        controller = (ROOT / "tools/phnix_ota/phnix_local_ota_controller.py").read_text(
            encoding="utf-8"
        )
        loss_branch = controller.split("if monitoring_lost and not monitoring_loss_announced:", 1)[1]
        detach = loss_branch.index('"monitoring-detached-passive"')
        clean_return = loss_branch.index("return", detach)
        next_probe = loss_branch.index('adb.run("get-state"', detach)
        self.assertLess(detach, clean_return)
        self.assertLess(clean_return, next_probe)
        event = loss_branch[detach:clean_return]
        for field in (
            "phase=", "service_pid=", "offset=", "transfer_started=",
            "original_service_authoritative=",
        ):
            self.assertIn(field, event)


if __name__ == "__main__":
    unittest.main()
