from __future__ import annotations

import sys
import time
from html import escape

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QToolTip

import foxair_updater_lte_diagnostics as lte
from updater.common.adb_transport import AdbClient
from updater.common.network_operators import OperatorIdentity, home_operator_from_imsi, lookup_operator
from updater.common.phnix_modem_info import PhnixModemInfo, read_process_memory


OTA_COUNTER_TOOLTIP = (
    "Vom LTE-Modul gezählte OTA-Aufträge. Der Zähler wird bereits beim Übernehmen "
    "der OTA-Dateiinformationen erhöht und entspricht daher nicht zwingend der "
    "Anzahl erfolgreicher oder unterschiedlicher Firmware-Updates."
)
UPLINK_COUNTER_TOOLTIP = (
    "Herstellerzähler Up-D-t. Zählt Uplink-Kommunikations-/Datentelegramm-"
    "Ereignisse, keine Bytes oder Datenmenge."
)
ACTIVE_RESET_TOOLTIP = (
    "Herstellerzähler Active-Reset-t. Wird erhöht, wenn phnixIot4G selbst einen "
    "vollständigen Modem/Linux-Reboot auslöst, z. B. nach mehr als 30 Minuten ohne "
    "Aliyun/MQTT-Verbindung oder nach einem Remote-RESET-Befehl. Ein normaler "
    "Neustart bzw. Kill des phnixIot4G-Prozesses erhöht den Zähler nicht."
)
POWER_RESET_TOOLTIP = (
    "Herstellerzähler Power-Reset-t. Der analysierte Build erhöht ihn bei jedem "
    "Start von phnixIot4G; der Wert ist daher kein reiner Stromausfallzähler."
)

RS485_RUNTIME_ADDRESS = 0x98914
RS485_RUNTIME_SIZE = 24

_POST_MQTT_GUARD_PHASES = {
    "c350-probe-attaching",
    "waiting-for-yield-loop",
    "c350-parser-injection",
    "parser-injection",
    "accepted",
    "c350-sent",
    "c350",
    "c357",
    "c5a8",
    "success-report",
    "success",
    "c350-same-version",
    "same-version",
}
_MQTT_GUARD_RELEASE_EVENTS = {
    "services-restored",
    "original-state-released",
    "hook-stopped",
}


class MainWindow(lte.MainWindow):
    """Presentation refinements for operator identity and OTA counters."""

    def __init__(self):
        self._rs485_runtime: tuple[int, int, int] | None = None
        self._ota_elapsed_started_at: float | None = None
        super().__init__()
        self._ota_elapsed_timer = QTimer(self)
        self._ota_elapsed_timer.setInterval(1000)
        self._ota_elapsed_timer.timeout.connect(self._update_ota_elapsed)

    def _update(self):
        widget = super()._update()
        layout = widget.layout()
        progress_index = layout.indexOf(self.progress)
        if progress_index >= 0:
            layout.takeAt(progress_index)
            row = QHBoxLayout()
            row.addWidget(self.progress, 1)
            self.progress_percent_label = QLabel("0 %")
            self.progress.valueChanged.connect(
                lambda value: self.progress_percent_label.setText(f"{value} %")
            )
            row.addWidget(self.progress_percent_label)
            self.ota_elapsed_label = QLabel("Verstrichen: --:--")
            elapsed_font = self.ota_elapsed_label.font()
            elapsed_font.setPointSize(max(12, elapsed_font.pointSize() + 2))
            elapsed_font.setBold(True)
            self.ota_elapsed_label.setFont(elapsed_font)
            self.ota_elapsed_label.setToolTip(
                "Reine Count-up-Anzeige ab dem ersten sicher nach der lokalen MQTT-Sperre "
                "beobachteten OTA-Zustand. Keine automatische Bewertung oder Abbruchlogik."
            )
            row.addWidget(self.ota_elapsed_label)
            layout.insertLayout(progress_index, row)
        return widget

    def _start_ota_elapsed(self) -> None:
        if self._ota_elapsed_started_at is not None:
            return
        self._ota_elapsed_started_at = time.monotonic()
        self._update_ota_elapsed()
        self._ota_elapsed_timer.start()

    def _stop_ota_elapsed(self) -> None:
        self._ota_elapsed_timer.stop()
        self._update_ota_elapsed()

    def _update_ota_elapsed(self) -> None:
        if not hasattr(self, "ota_elapsed_label"):
            return
        if self._ota_elapsed_started_at is None:
            self.ota_elapsed_label.setText("Verstrichen: --:--")
            return
        elapsed = max(0, int(time.monotonic() - self._ota_elapsed_started_at))
        minutes, seconds = divmod(elapsed, 60)
        self.ota_elapsed_label.setText(f"Verstrichen: {minutes:02d}:{seconds:02d}")

    def _reset_flow(self, title: str, *, transfer_expected: bool = False):
        if hasattr(self, "_ota_elapsed_timer"):
            self._ota_elapsed_timer.stop()
        self._ota_elapsed_started_at = None
        if hasattr(self, "ota_elapsed_label"):
            self.ota_elapsed_label.setText("Verstrichen: --:--")
        super()._reset_flow(title, transfer_expected=transfer_expected)

    def _handle_phase(self, phase: str):
        super()._handle_phase(phase)
        if phase in _POST_MQTT_GUARD_PHASES:
            self._start_ota_elapsed()
        if phase == "success":
            self._stop_ota_elapsed()

    def _handle_record(self, record: dict):
        super()._handle_record(record)
        hook = record.get("hook") if isinstance(record.get("hook"), dict) else {}
        if hook.get("phase") == "success" and hook.get("terminal") is True:
            self._stop_ota_elapsed()
        if record.get("event") in _MQTT_GUARD_RELEASE_EVENTS:
            self._stop_ota_elapsed()

    def _modem_info_page(self):
        widget = super()._modem_info_page()
        # QLabel exposes linkHovered, which gives us a real field-specific
        # tooltip without turning the whole diagnostics panel into a tooltip.
        self.modem_info_text.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse
        )
        self.modem_info_text.setOpenExternalLinks(False)
        self.modem_info_text.linkHovered.connect(self._diagnostic_link_hovered)
        self.modem_info_text.linkActivated.connect(lambda _href: None)
        return widget

    def _diagnostic_link_hovered(self, href: str) -> None:
        tooltips = {
            "ota-counter": OTA_COUNTER_TOOLTIP,
            "uplink-counter": UPLINK_COUNTER_TOOLTIP,
            "active-reset": ACTIVE_RESET_TOOLTIP,
            "power-reset": POWER_RESET_TOOLTIP,
        }
        text = tooltips.get(href)
        if text:
            QToolTip.showText(QCursor.pos(), text, self.modem_info_text)
        else:
            QToolTip.hideText()

    @staticmethod
    def _operator(identity: OperatorIdentity | None) -> str:
        if identity is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        if identity.name:
            return f"{escape(identity.name)} <span style=\"color:#667085;\">({identity.code})</span>"
        return f'<span style="color:#667085;">unbekannter Betreiber ({identity.code})</span>'

    @staticmethod
    def _csq_with_rssi(value: int | float | None, *, decimals: int = 0) -> str:
        if value is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        numeric = float(value)
        if numeric <= 0:
            return '<span style="color:#667085;">nicht verfügbar (CSQ 0 = ungültiger/Initialwert)</span>'
        text = f"{numeric:.{decimals}f}" if decimals else str(int(numeric))
        text = text.replace(".", ",")
        if 1 <= numeric < 31:
            rssi = round(-113 + 2 * numeric)
            return f"CSQ {text} / 31 (~ {rssi} dBm)"
        if numeric == 31:
            return f"CSQ {text} / 31 (≥ -51 dBm)"
        return f"CSQ {text} (Rohwert außerhalb 0…31)"

    @staticmethod
    def _replace_html_line(html: str, prefix: str, replacement: str) -> str:
        start = html.find(prefix)
        if start < 0:
            return html
        end = html.find("<br>", start)
        if end < 0:
            return html
        return html[:start] + replacement + html[end + 4:]

    @staticmethod
    def _age(value: int | None) -> str:
        if value is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        return f"vor {value} s"

    def _board_service_health(self, info: PhnixModemInfo) -> str:
        age = self._rs485_runtime[0] if self._rs485_runtime is not None else None
        if age is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        if (info.error_status or 0) & (1 << 5) or age > 420:
            return (
                f'<span style="color:{lte.desktop.app.RED};"><b>seit {age} s ohne Bestätigung</b></span>'
            )
        return f'<span style="color:{lte.desktop.app.GREEN};"><b>OK</b></span>'

    def _rs485_error_status(self, info: PhnixModemInfo) -> str:
        status = info.error_status
        if status is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        active = []
        if status & (1 << 5):
            active.append("Board-Service-/Health-Timeout")
        if status & (1 << 6):
            active.append("kein 0x63-Traffic seit ~420 s")
        if status & (1 << 12):
            active.append("kein CRC-gültiges 0x63-Frame seit ~420 s")
        if not active:
            return f'<span style="color:{lte.desktop.app.GREEN};"><b>OK</b></span>'
        return (
            f'<span style="color:{lte.desktop.app.RED};"><b>'
            + escape("; ".join(active))
            + "</b></span>"
        )

    @staticmethod
    def _technical_error_messages(info: PhnixModemInfo) -> list[str]:
        if info.error_status is None:
            return []
        mapping = {
            0: "485-Verbindungsfehler",
            1: "Adressfehler",
            3: "No PK",
            4: "Signal-/CSQ-Problem",
            5: "Board-Service-/Health-Timeout",
            6: "seit ~420 s kein 0x63-Mainboardtraffic",
            7: "CRC-Fehler",
            8: "UART485 Init-/Startproblem",
            10: "Aliyun/MQTT aktuell nicht verbunden",
            12: "seit ~420 s kein CRC-gültiges 0x63-Frame",
        }
        result = [text for bit, text in mapping.items() if info.error_status & (1 << bit)]
        known_mask = sum(1 << bit for bit in mapping)
        unknown_mask = info.error_status & ~known_mask
        if unknown_mask:
            unknown = [str(bit) for bit in range(32) if unknown_mask & (1 << bit)]
            result.append("Unbekannte Fehlerbits: " + ", ".join(unknown))
        return result

    def _read_rs485_runtime(self, info: PhnixModemInfo) -> None:
        self._rs485_runtime = None
        if info.pid is None:
            return
        adb = self._adb_path()
        if adb is None:
            return
        try:
            client = AdbClient(adb, env=self._process_env())
            raw = read_process_memory(
                client,
                info.pid,
                RS485_RUNTIME_ADDRESS,
                RS485_RUNTIME_SIZE,
            )
            self._rs485_runtime = (
                int.from_bytes(raw[0:4], "little"),
                int.from_bytes(raw[12:16], "little"),
                int.from_bytes(raw[20:24], "little"),
            )
        except Exception as exc:
            info.read_errors.append("RS485-Runtime-Diagnose: " + str(exc))

    def _modem_info_result(self, value: object):
        if isinstance(value, PhnixModemInfo):
            self._read_rs485_runtime(value)
        else:
            self._rs485_runtime = None
        super()._modem_info_result(value)

    def _modem_info_html(self, info: PhnixModemInfo) -> str:
        html = super()._modem_info_html(info)

        home = home_operator_from_imsi(info.imsi)
        current = (
            lookup_operator(info.mcc, info.mnc)
            if info.current_plmn_valid == 1
            else None
        )

        imsi_line = f"IMSI: <b>{self._fmt(info.imsi)}</b><br>"
        html = html.replace(
            imsi_line,
            imsi_line + f"Heimatnetz (aus IMSI): <b>{self._operator(home)}</b><br>",
            1,
        )

        plmn_line = f"Netzkennung MCC / MNC: <b>{self._plmn(info)}</b><br>"
        html = html.replace(
            plmn_line,
            plmn_line
            + f"Aktueller Netzbetreiber: <b>{self._operator(current)}</b><br>",
            1,
        )
        html = html.replace("Netzbeschreibung: <b>", "Netzbeschreibung (Modem): <b>", 1)

        stats = info.statistics
        avg = stats.average_csq
        signal_values = (
            ("Signal aktuell", stats.current_csq, 0),
            ("Signal Ø", avg, 1),
            ("Signal Maximum", stats.strongest_csq, 0),
            ("Signal Minimum", stats.weakest_csq, 0),
        )
        for label, value, decimals in signal_values:
            old = f"{label}: <b>{self._csq(value, decimals=decimals)}</b><br>"
            new = f"{label}: <b>{self._csq_with_rssi(value, decimals=decimals)}</b><br>"
            html = html.replace(old, new, 1)

        upload_value = self._fmt_count(stats.upload_count)
        html = html.replace(
            f"Uploadzähler: <b>{upload_value}</b><br>",
            '<a href="uplink-counter" style="color:#344054;text-decoration:none;">'
            "Uplink-Telegramme ⓘ</a>: "
            f"<b>{upload_value}</b><br>",
            1,
        )
        html = html.replace(
            f"Downloadzähler: <b>{self._fmt_count(stats.download_count)}</b><br>",
            f"Downlink-Telegramme: <b>{self._fmt_count(stats.download_count)}</b><br>",
            1,
        )
        html = html.replace(
            f"DTU-OTA-Zähler: <b>{self._fmt_count(stats.dtu_ota_count)}</b><br>",
            f"DTU-OTA-Vorgänge: <b>{self._fmt_count(stats.dtu_ota_count)}</b><br>",
            1,
        )

        ota_value = self._fmt_count(stats.mainboard_ota_count)
        old_ota = f"Mainboard-OTA-Zähler: <b>{ota_value}</b><br>"
        new_ota = (
            '<a href="ota-counter" style="color:#344054;text-decoration:none;">'
            "Mainboard OTA-Vorgänge ⓘ</a>: "
            f"<b>{ota_value}</b><br>"
        )
        html = html.replace(old_ota, new_ota, 1)

        power_value = self._fmt_count(stats.power_reset_count)
        html = html.replace(
            f"Power-Reset-Zähler: <b>{power_value}</b><br>",
            '<a href="power-reset" style="color:#344054;text-decoration:none;">'
            "phnixIot4G-Starts (Power-Reset-t) ⓘ</a>: "
            f"<b>{power_value}</b><br>",
            1,
        )
        active_value = self._fmt_count(stats.active_reset_count)
        html = html.replace(
            f"Active-/Software-Reset-Zähler: <b>{active_value}</b><br>",
            '<a href="active-reset" style="color:#344054;text-decoration:none;">'
            "Vom LTE-Dienst ausgelöste Reboots ⓘ</a>: "
            f"<b>{active_value}</b><br>",
            1,
        )

        service_age = self._rs485_runtime[0] if self._rs485_runtime is not None else None
        traffic_age = self._rs485_runtime[1] if self._rs485_runtime is not None else None
        valid_age = self._rs485_runtime[2] if self._rs485_runtime is not None else None
        rs485_block = (
            "<h3>RS485 / Mainboard</h3>"
            f"Board-Service-Health: {self._board_service_health(info)}<br>"
            f"Letzter 0x63-Traffic: <b>{self._age(traffic_age)}</b><br>"
            f"Letztes gültiges 0x63-Frame: <b>{self._age(valid_age)}</b><br>"
            f"RS485-Fehlerstatus: {self._rs485_error_status(info)}"
        )
        html = self._replace_html_line(html, "Mainboard / RS485: ", rs485_block)

        if info.error_status is None:
            cloud_status = '<span style="color:#667085;">nicht verfügbar</span>'
        elif info.error_status & (1 << 10):
            cloud_status = (
                f'<span style="color:{lte.desktop.app.RED};"><b>Aliyun/MQTT nicht verbunden</b></span>'
            )
        else:
            cloud_status = (
                f'<span style="color:{lte.desktop.app.GREEN};">kein Aliyun/MQTT-Offlinebit gesetzt</span>'
            )
        html = self._replace_html_line(
            html,
            "Cloud-Fehlerbits: ",
            f"Cloud-/MQTT-Fehlerstatus: {cloud_status}",
        )

        old_errors = info.error_messages
        old_error_text = (
            "<br>".join("• " + escape(item) for item in old_errors)
            if old_errors
            else "keine bekannten Fehlerbits gesetzt"
        )
        technical_errors = self._technical_error_messages(info)
        technical_text = (
            "<br>".join("• " + escape(item) for item in technical_errors)
            if technical_errors
            else "keine bekannten Fehlerbits gesetzt"
        )
        html = html.replace(
            f"Fehlertexte:<br>{old_error_text}<br>",
            f"Fehlerstatus technisch:<br>{technical_text}<br>",
            1,
        )
        return html


def main():
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("FoxAir Updater")
    qt_app.setOrganizationName("FoxAir")
    icon = lte.desktop.app.base.root_dir() / "app_icon.ico"
    if icon.is_file():
        qt_app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
