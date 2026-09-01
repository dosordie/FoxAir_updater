import time
import unittest
from pathlib import Path

from updater.common.phnix_debug import PhnixDebugCapture, SerialCompletionSequence


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
        self.assertIn("Das Firmwareupdate wurde nicht gestartet", lte)
        self.assertLess(lte.index("self._start_automatic_logs(manifest)"), lte.index("restart_phnix_iot_service("))


if __name__ == "__main__":
    unittest.main()
