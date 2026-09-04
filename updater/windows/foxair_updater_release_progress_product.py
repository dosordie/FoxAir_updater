from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import foxair_updater_gui as base
import foxair_updater_release_product as release


class MainWindow(release.MainWindow):
    """Release UI with transfer-gated visible firmware progress.

    The DTU may populate OTA_INFO offset/length while the update handshake is
    still being prepared.  Those counters remain useful diagnostics, but the
    end-user progress bar must not count up until the runner has crossed the
    real firmware-transfer boundary (C5A8 / transfer_started).

    Only the *beginning* of the visible counter is gated here.  Once transfer
    has started, the existing progress/end semantics remain unchanged.
    """

    def _render_runner_status(self, status: dict) -> None:
        super()._render_runner_status(status)

        if status.get("transfer_started") is True:
            return

        # Before C5A8 the displayed counter stays at zero even if OTA_INFO
        # already contains a non-zero offset/length during handshake/setup.
        self.progress.setValue(0)
        self.progress.setFormat("0 % – LTE-Modem")


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
