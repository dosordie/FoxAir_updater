from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import foxair_updater_release_product as release


PASSIVE_STATUS_STALE_SECONDS = 10.0
RECONCILE_RETRY_SECONDS = 10.0
AUTO_CLEANUP_RESULTS = {"success", "same-version"}
AUTO_DIAGNOSTIC_RESULT_TYPES = {
    "recovery-required",
    "reboot-detected",
    "runner-lost",
    "failed",
}


class MainWindow(release.MainWindow):
    """Final release behavior for low-load polling and automatic diagnostics.

    Normal two-second GUI refreshes only read the durable status JSON.  The
    DTU-side classifier is invoked only after the same status timestamp has
    remained unchanged for at least ten seconds, and then at most once per ten
    seconds until progress resumes.  This keeps the display responsive without
    spawning a classifier shell on every GUI refresh.

    Every terminal result and every guarded recovery-required state is archived
    automatically.  Only successful/same-version terminal runs continue through
    the existing ACK + cleanup path; failure/recovery archives never alter or
    delete the retained DTU state.
    """

    def __init__(self):
        self._passive_status_updated_at: int | None = None
        self._passive_status_same_since: float | None = None
        self._passive_last_reconcile_at: float | None = None
        self._auto_finalize_cleanup_allowed = False
        self._auto_diagnostic_host_log: Path | None = None
        super().__init__()

    @staticmethod
    def _diagnostics_core_path() -> Path:
        # Use the release-only scope wrapper so global /tmp GDB logs are only
        # archived when they can be tied to this exact autonomous run.
        return release.base.backend_dir() / "updater/dtu_ota/diagnostics_current_run.py"

    def _poll_runner_status(self):
        if self.busy or not self._runner_active or not self._runner_run_id:
            return

        now = time.monotonic()
        stale = (
            self._passive_status_same_since is not None
            and now - self._passive_status_same_since >= PASSIVE_STATUS_STALE_SECONDS
        )
        reconcile_due = stale and (
            self._passive_last_reconcile_at is None
            or now - self._passive_last_reconcile_at >= RECONCILE_RETRY_SECONDS
        )

        # Keep the manual status button visually stable, matching the inherited
        # passive-poll presentation behavior.
        self._passive_runner_poll = True
        args = ["status", "--run-id", self._runner_run_id]
        if reconcile_due:
            self._passive_last_reconcile_at = now
        else:
            args.append("--no-reconcile")
        self._run_runner("runner-status", *args)

    def _render_runner_status(self, status: dict) -> None:
        updated_at = status.get("updated_at")
        now = time.monotonic()
        if isinstance(updated_at, int):
            if updated_at != self._passive_status_updated_at:
                self._passive_status_updated_at = updated_at
                self._passive_status_same_since = now
                self._passive_last_reconcile_at = None
            elif self._passive_status_same_since is None:
                self._passive_status_same_since = now

        super()._render_runner_status(status)

    def _schedule_terminal_auto_finalize(self, status: dict) -> None:
        run_id = str(status.get("run_id") or "").strip()
        result_type = str(status.get("result_type") or "").strip()
        recovery = str(status.get("recovery") or "").strip()
        terminal = status.get("terminal") is True
        diagnostic_worthy = (
            terminal
            or recovery == "required"
            or result_type in AUTO_DIAGNOSTIC_RESULT_TYPES
        )
        if (
            not diagnostic_worthy
            or not run_id
            or run_id in self._auto_finalize_started
        ):
            return

        self._auto_finalize_cleanup_allowed = (
            terminal and result_type in AUTO_CLEANUP_RESULTS
        )
        self._auto_finalize_started.add(run_id)
        QTimer.singleShot(300, lambda rid=run_id: self._start_terminal_auto_archive(rid))

    def _start_terminal_auto_archive(self, run_id: str) -> None:
        if self.busy:
            QTimer.singleShot(300, lambda rid=run_id: self._start_terminal_auto_archive(rid))
            return

        adb = self._require_adb()
        core = self._diagnostics_core_path()
        if not adb or not core.is_file():
            self._auto_finalize_started.discard(run_id)
            self._auto_finalize_cleanup_allowed = False
            self._auto_finalize_failed(
                "Diagnosepaket nicht automatisch gespeichert",
                "Das automatische Diagnosearchiv konnte nicht gestartet werden. Die Daten auf "
                "dem LTE-Modem bleiben unverändert erhalten; der manuelle Diagnose-Export bleibt verfügbar.",
            )
            return

        log_directory = self._diagnostic_log_directory()
        archive = log_directory / f"FoxAir_DTU_Logs_{run_id}.zip"
        self._auto_finalize_run_id = run_id
        self._auto_finalize_archive = archive
        self._auto_cleanup_retry_visible = False
        self._log(f"[DTU Runner] automatisches Diagnosearchiv für {run_id} wird erstellt.")

        host_log = release.base.data_dir() / f"diagnostics-auto-{run_id}.log"
        try:
            host_log.write_text(self.log.toPlainText(), encoding="utf-8")
            self._auto_diagnostic_host_log = host_log
        except OSError:
            self._auto_diagnostic_host_log = None

        command = [
            str(release.base.backend_python()),
            str(core),
            "--adb",
            str(adb),
            "--output",
            str(archive),
            "--host-log-dir",
            str(log_directory),
            "--app-version",
            release.base.APP_VERSION,
            "--run-id",
            run_id,
        ]
        if self._auto_diagnostic_host_log is not None:
            command += ["--host-log", str(self._auto_diagnostic_host_log)]
        self._run("runner-auto-diagnostics", command, str(release.base.backend_dir()))

    def _remove_auto_diagnostic_host_log(self) -> None:
        host_log = self._auto_diagnostic_host_log
        self._auto_diagnostic_host_log = None
        if isinstance(host_log, Path):
            try:
                host_log.unlink(missing_ok=True)
            except OSError:
                pass

    def _done(self, op, code, output):
        if op != "runner-auto-diagnostics":
            super()._done(op, code, output)
            return

        # Successful/same-version runs retain the already proven automatic
        # archive -> ACK -> cleanup flow from release_product.
        if self._auto_finalize_cleanup_allowed:
            try:
                super()._done(op, code, output)
            finally:
                self._remove_auto_diagnostic_host_log()
            return

        # Failure/recovery runs are archive-only.  Never ACK or clean them: the
        # retained runner/OTA state may still be needed for recovery analysis.
        super()._done("handled-result", code, output)
        parsed = self._last_json_record(output)
        run_id = self._auto_finalize_run_id
        archive = self._auto_finalize_archive
        archive_ok = isinstance(archive, Path) and archive.is_file()
        self._remove_auto_diagnostic_host_log()

        if code == 0 and parsed and parsed.get("ok") is True and run_id and archive_ok:
            self._log(f"[DTU Runner] Diagnosepaket automatisch gespeichert: {archive}")
            status_widget = getattr(self, "runner_status_text", None)
            if status_widget is not None:
                current = status_widget.text()
                status_widget.setText(
                    current
                    + "<br><br><b>✓ Diagnosepaket automatisch lokal gespeichert.</b>"
                    + f"<br><small>{archive}</small>"
                    + "<br><small>Fehler-/Recovery-Daten auf dem LTE-Modem wurden nicht gelöscht.</small>"
                )
            self._auto_finalize_run_id = None
            self._auto_finalize_archive = None
            self._auto_finalize_cleanup_allowed = False
            self._buttons()
            return

        self._auto_finalize_cleanup_allowed = False
        self._auto_finalize_failed(
            "Diagnosepaket nicht automatisch gespeichert",
            "Das automatische Diagnosepaket konnte nicht eindeutig lokal gespeichert werden. "
            "Die Daten auf dem LTE-Modem bleiben unverändert erhalten; der manuelle Diagnose-Export bleibt verfügbar.",
        )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("FoxAir Updater")
    app.setOrganizationName("FoxAir")
    icon = release.base.root_dir() / "app_icon.ico"
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
