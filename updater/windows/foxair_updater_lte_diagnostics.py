from __future__ import annotations

import sys
import threading
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import foxair_updater_desktop as desktop
from updater.common.adb_transport import AdbClient
from updater.common.phnix_modem_info import PhnixModemInfo, format_seconds, read_phnix_modem_info


class MainWindow(desktop.MainWindow):
    """Desktop GUI extension for read-only LTE/SIM/cloud diagnostics."""

    def __init__(self):
        self._last_modem_info: PhnixModemInfo | None = None
        super().__init__()

    def _modem_info_page(self):
        widget = QWidget()
        outer = QVBoxLayout(widget)

        note = QLabel(
            "<b>Read-only Diagnose des laufenden phnixIot4G-Prozesses und des Linux-Netzwerks.</b><br>"
            "RAM-Werte werden ausschließlich per ADB aus <code>/proc/&lt;PID&gt;/mem</code> gelesen. "
            "Die Seite öffnet <b>nicht</b> <code>/dev/ttyHSL2</code>, sendet keine zusätzlichen "
            "Modbus-/RS485-Telegramme und schreibt nicht in den Prozessspeicher. "
            "Mobilfunk-IP und Gateway stammen read-only aus Linux-Netzwerkdaten."
        )
        note.setWordWrap(True)
        outer.addWidget(note)

        row = QHBoxLayout()
        self.modem_refresh_btn = desktop.QPushButton("Modem-Informationen neu lesen")
        self.modem_refresh_btn.clicked.connect(self._refresh_modem_info)
        row.addWidget(self.modem_refresh_btn)
        self.modem_read_status = QLabel("Noch nicht gelesen.")
        self.modem_read_status.setWordWrap(True)
        row.addWidget(self.modem_read_status, 1)
        outer.addLayout(row)

        self.show_cloud_secrets = QCheckBox("Cloud-Secrets anzeigen")
        self.show_cloud_secrets.setToolTip(
            "Secrets werden nur in dieser Ansicht eingeblendet und nicht automatisch protokolliert."
        )
        self.show_cloud_secrets.toggled.connect(self._rerender_modem_info)
        outer.addWidget(self.show_cloud_secrets)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        self.modem_info_text = QLabel(
            '<span style="color:#667085;">Noch keine Modem-Diagnosedaten gelesen.</span>'
        )
        self.modem_info_text.setWordWrap(True)
        self.modem_info_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.modem_info_text.setStyleSheet(
            "QLabel{background:#f7f8fa;border:1px solid #d0d5dd;padding:10px;}"
        )
        content_layout.addWidget(self.modem_info_text)
        content_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        return widget

    def _refresh_modem_info(self):
        if self.busy or self._modem_info_running:
            return
        adb = self._require_adb()
        if not adb:
            return

        self._modem_info_running = True
        self.modem_read_status.setStyleSheet("")
        self.modem_read_status.setText("Lese read-only Modem-, SIM-, Mobilfunk- und Cloudinformationen …")
        self._buttons()

        def work():
            try:
                client = AdbClient(adb, env=self._process_env())
                value = read_phnix_modem_info(client)
            except Exception as error:
                self._modem_signals.error.emit(str(error))
            else:
                self._modem_signals.result.emit(value)

        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _fmt(value) -> str:
        if value is None or value == "":
            return '<span style="color:#667085;">nicht verfügbar</span>'
        return escape(str(value))

    @staticmethod
    def _fmt_count(value: int | None) -> str:
        if value is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        return f"{value:,}".replace(",", ".")

    @staticmethod
    def _known_one(value: int | None, yes_text: str = "Ja") -> str:
        if value is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        if value == 1:
            return yes_text
        return f"unbekannt ({value})"

    @staticmethod
    def _sim_state(value: int | None) -> str:
        if value is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        if value == 7:
            return "READY"
        return f"unbekannt ({value})"

    @staticmethod
    def _rat(value: int | None) -> str:
        if value is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        if value == 8:
            return "LTE"
        return f"unbekannt ({value})"

    @staticmethod
    def _csq(value: int | float | None, *, decimals: int = 0) -> str:
        if value is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        numeric = float(value)
        text = f"{numeric:.{decimals}f}" if decimals else str(int(numeric))
        if 0 <= numeric <= 31:
            return f"{text} / 31"
        return f"{text} (Rohwert außerhalb 0…31)"

    @staticmethod
    def _roaming(info: PhnixModemInfo) -> str:
        if info.roaming_valid != 1:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        mapping = {0: "Ja", 1: "Nein", 2: "FLASHING"}
        if info.roaming_indicator is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        return mapping.get(info.roaming_indicator, f"unbekannt ({info.roaming_indicator})")

    @staticmethod
    def _plmn(info: PhnixModemInfo) -> str:
        if info.current_plmn_valid != 1 or info.mcc is None or info.mnc is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        return f"{info.mcc:03d} / {info.mnc:02d}"

    @staticmethod
    def _lac(info: PhnixModemInfo) -> str:
        if info.lac is None or info.lac == 0xFFFE:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        return str(info.lac)

    def _secret(self, value: str | None) -> str:
        if not value:
            return '<span style="color:#667085;">nicht geladen</span>'
        if self.show_cloud_secrets.isChecked():
            return f"<code>{escape(value)}</code>"
        return "<code>••••••••••••••••</code>"

    @staticmethod
    def _mqtt(info: PhnixModemInfo) -> str:
        cloud = info.cloud
        if cloud.pclient_pointer is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        if cloud.pclient_pointer == 0:
            return '<span style="color:#667085;">Nicht initialisiert</span>'
        if cloud.mqtt_state == 2:
            return f'<span style="color:{desktop.app.GREEN};"><b>Verbunden</b></span>'
        if cloud.mqtt_state is None:
            return '<span style="color:#667085;">Status nicht verfügbar</span>'
        return (
            f'<span style="color:{desktop.app.YELLOW};">Nicht verbunden / Verbindungsaufbau '
            f"(State {cloud.mqtt_state})</span>"
        )

    def _modem_info_html(self, info: PhnixModemInfo) -> str:
        stats = info.statistics
        avg = stats.average_csq

        if info.rs485_ok is True:
            rs485 = (
                f'<span style="color:{desktop.app.GREEN};"><b>OK</b> – keine bekannten '
                "RS485/Mainboard-Fehlerbits gesetzt</span>"
            )
        elif info.rs485_ok is False:
            rs485 = f'<span style="color:{desktop.app.RED};"><b>Fehler gemeldet</b></span>'
        else:
            rs485 = '<span style="color:#667085;">nicht verfügbar</span>'

        if info.cloud_error is True:
            error_cloud = f'<span style="color:{desktop.app.RED};"><b>Fehlerbit gesetzt</b></span>'
        elif info.cloud_error is False:
            error_cloud = (
                f'<span style="color:{desktop.app.GREEN};">kein bekannter Cloud-Fehler '
                "in ErrorStatue gesetzt</span>"
            )
        else:
            error_cloud = '<span style="color:#667085;">nicht verfügbar</span>'

        error_bitmap = (
            f"0x{info.error_status:08X}" if info.error_status is not None else "nicht verfügbar"
        )
        errors = info.error_messages
        error_text = (
            "<br>".join("• " + escape(item) for item in errors)
            if errors
            else "keine bekannten Fehlerbits gesetzt"
        )

        rows = [
            "<h3>Mainboard</h3>",
            f"Firmware: <b>{self._fmt(info.firmware_version)}</b><br>",
            f"Softwarecode: <b>{self._fmt(info.software_code)}</b><br>",
            f"Hardwarecode: <b>{self._fmt(info.hardware_code)}</b><br>",
            f"Hardwareversion: <b>{self._fmt(info.hardware_version)}</b><br>",
            "<h3>Modem</h3>",
            f"Modell: <b>{self._fmt(info.modem_model)}</b><br>",
            f"IMEI: <b>{self._fmt(info.imei)}</b><br>",
            "<h3>SIM</h3>",
            f"ICCID: <b>{self._fmt(info.iccid)}</b><br>",
            f"IMSI: <b>{self._fmt(info.imsi)}</b><br>",
            f"SIM vorhanden: <b>{self._known_one(info.sim.card_status)}</b><br>",
            f"SIM Status: <b>{self._sim_state(info.sim.app_state)}</b><br>",
            f"SIM App-Type (roh): <b>{self._fmt(info.sim.app_type)}</b><br>",
            "<h3>Mobilfunk</h3>",
            f"Mobilfunkstandard: <b>{self._rat(info.serving.radio_interface_0)}</b><br>",
            f"Registriert: <b>{self._known_one(info.serving.registration_state)}</b><br>",
            f"CS Attach: <b>{self._known_one(info.serving.cs_attach_state)}</b><br>",
            f"PS Attach: <b>{self._known_one(info.serving.ps_attach_state)}</b><br>",
            f"Netzkennung MCC / MNC: <b>{self._plmn(info)}</b><br>",
            f"Netzbeschreibung: <b>{self._fmt(info.network_description if info.current_plmn_valid == 1 else None)}</b><br>",
            f"Roaming: <b>{self._roaming(info)}</b><br>",
            f"Cell-ID: <b>{self._fmt(info.cell_id)}</b><br>",
            f"LAC/TAC: <b>{self._lac(info)}</b><br>",
            f"Signal aktuell: <b>{self._csq(stats.current_csq)}</b><br>",
            f"Signal Ø: <b>{self._csq(avg, decimals=1)}</b><br>",
            f"Signal Maximum: <b>{self._csq(stats.strongest_csq)}</b><br>",
            f"Signal Minimum: <b>{self._csq(stats.weakest_csq)}</b><br>",
            "<h3>Netzwerk</h3>",
            f"Mobilfunkinterface: <b>{self._fmt(info.network.interface)}</b><br>",
            f"Mobilfunk-IP / PDP-IP: <b>{self._fmt(info.network.ip_address)}</b><br>",
            f"Präfix: <b>{('/' + str(info.network.prefix_length)) if info.network.prefix_length is not None else self._fmt(None)}</b><br>",
            f"Gateway: <b>{self._fmt(info.network.gateway)}</b><br>",
            "<h3>Cloud</h3>",
            f"MQTT / Cloud: {self._mqtt(info)}<br>",
            f"Aliyun DeviceName: <b>{self._fmt(info.cloud.device_name)}</b><br>",
            f"ProductKey: <b>{self._fmt(info.cloud.product_key)}</b><br>",
            f"DeviceSecret: {self._secret(info.cloud.device_secret)}<br>",
            f"ProductSecret: {self._secret(info.cloud.product_secret)}<br>",
            f"MQTT State (roh): <b>{self._fmt(info.cloud.mqtt_state)}</b><br>",
            f"MQTT_init_signal (diagnostisch): <b>{self._fmt(info.cloud.mqtt_init_signal)}</b><br>",
            "<h3>Statistik / Fehler</h3>",
            f"Gesamtbetriebszeit: <b>{escape(format_seconds(stats.work_time))}</b><br>",
            f"Gesamt-Onlinezeit: <b>{escape(format_seconds(stats.online_time))}</b><br>",
            f"Aktuelle Laufzeit: <b>{escape(format_seconds(stats.current_work_time))}</b><br>",
            f"Aktuelle Onlinezeit: <b>{escape(format_seconds(stats.current_online_time))}</b><br>",
            f"Uploadzähler: <b>{self._fmt_count(stats.upload_count)}</b><br>",
            f"Downloadzähler: <b>{self._fmt_count(stats.download_count)}</b><br>",
            f"DTU-OTA-Zähler: <b>{self._fmt_count(stats.dtu_ota_count)}</b><br>",
            f"Mainboard-OTA-Zähler: <b>{self._fmt_count(stats.mainboard_ota_count)}</b><br>",
            f"Power-Reset-Zähler: <b>{self._fmt_count(stats.power_reset_count)}</b><br>",
            f"Active-/Software-Reset-Zähler: <b>{self._fmt_count(stats.active_reset_count)}</b><br>",
            f"Mainboard / RS485: {rs485}<br>",
            f"Cloud-Fehlerbits: {error_cloud}<br>",
            f"ErrorStatue Bitmap: <code>{escape(error_bitmap)}</code><br>",
            f"Fehlertexte:<br>{error_text}<br>",
        ]

        if info.read_errors:
            rows.extend(
                [
                    "<h3>Hinweise zu unvollständigen Reads</h3>",
                    '<span style="color:#b26a00;">'
                    + "<br>".join("• " + escape(item) for item in info.read_errors)
                    + "</span>",
                ]
            )
        return "".join(rows)

    def _rerender_modem_info(self):
        if self._last_modem_info is not None:
            self.modem_info_text.setText(self._modem_info_html(self._last_modem_info))

    def _modem_info_result(self, value: object):
        self._modem_info_running = False
        if not isinstance(value, PhnixModemInfo):
            self._modem_info_error("Unerwarteter Modem-Info-Datentyp")
            return

        self._last_modem_info = value
        self.modem_info_text.setText(self._modem_info_html(value))
        if value.pid is None:
            self.modem_read_status.setStyleSheet(f"QLabel{{color:{desktop.app.RED};}}")
            self.modem_read_status.setText("phnixIot4G nicht lesbar – Werte nicht verfügbar.")
        elif value.read_errors:
            self.modem_read_status.setStyleSheet(f"QLabel{{color:{desktop.app.YELLOW};}}")
            self.modem_read_status.setText(
                f"PID {value.pid} gelesen – einzelne Werte sind nicht verfügbar."
            )
        else:
            self.modem_read_status.setStyleSheet(f"QLabel{{color:{desktop.app.GREEN};}}")
            self.modem_read_status.setText(
                f"PID {value.pid} – read-only Diagnose erfolgreich gelesen."
            )
        self._buttons()

    def _modem_info_error(self, message: str):
        self._modem_info_running = False
        self._last_modem_info = None
        self.modem_read_status.setStyleSheet(f"QLabel{{color:{desktop.app.RED};}}")
        self.modem_read_status.setText("Modem-Diagnose konnte nicht gelesen werden.")
        self.modem_info_text.setText(
            '<span style="color:#b42318;">' + escape(message) + "</span>"
        )
        # Error messages never contain decoded secret values.  Normal modem
        # diagnostic values are intentionally not copied into the application log.
        self._log("[Modem Info] " + message)
        self._buttons()


def main():
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("FoxAir Updater")
    qt_app.setOrganizationName("FoxAir")
    icon = desktop.app.base.root_dir() / "app_icon.ico"
    if icon.is_file():
        qt_app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
