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


if __name__ == "__main__":
    unittest.main()
