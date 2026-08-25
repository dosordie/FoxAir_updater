from __future__ import annotations

import sys
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import QApplication, QToolTip

import foxair_updater_lte_diagnostics as lte
from updater.common.network_operators import OperatorIdentity, home_operator_from_imsi, lookup_operator
from updater.common.phnix_modem_info import PhnixModemInfo


OTA_COUNTER_TOOLTIP = (
    "Vom LTE-Modul gezählte OTA-Aufträge. Der Zähler wird bereits beim Übernehmen "
    "der OTA-Dateiinformationen erhöht und entspricht daher nicht zwingend der "
    "Anzahl erfolgreicher oder unterschiedlicher Firmware-Updates."
)


class MainWindow(lte.MainWindow):
    """Presentation refinements for operator identity and OTA counters."""

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
        if href == "ota-counter":
            QToolTip.showText(QCursor.pos(), OTA_COUNTER_TOOLTIP, self.modem_info_text)
        else:
            QToolTip.hideText()

    @staticmethod
    def _operator(identity: OperatorIdentity | None) -> str:
        if identity is None:
            return '<span style="color:#667085;">nicht verfügbar</span>'
        if identity.name:
            return f"{escape(identity.name)} <span style=\"color:#667085;\">({identity.code})</span>"
        return f'<span style="color:#667085;">unbekannter Betreiber ({identity.code})</span>'

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

        ota_value = self._fmt_count(info.statistics.mainboard_ota_count)
        old_ota = f"Mainboard-OTA-Zähler: <b>{ota_value}</b><br>"
        new_ota = (
            '<a href="ota-counter" style="color:#344054;text-decoration:none;">'
            "Mainboard OTA-Vorgänge ⓘ</a>: "
            f"<b>{ota_value}</b><br>"
        )
        html = html.replace(old_ota, new_ota, 1)
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
