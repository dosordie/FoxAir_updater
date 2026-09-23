#!/usr/bin/env python3
"""Small curses front-end for the existing FoxAir simulator controller."""

from __future__ import annotations

import curses
import json
import os
from pathlib import Path
import subprocess
import textwrap
import time


INSTALL_DIR = Path(os.environ.get("FOXAIR_FAKE_ADB_INSTALL_DIR", "/opt/foxair-fake-adb"))
ADAPTER = INSTALL_DIR / "qemu_work_lab_backend.py"
CONTROL = INSTALL_DIR / "foxair-fake-adbctl"
STATE_DIR = Path(os.environ.get("FOXAIR_FAKE_ADB_STATE", "/var/lib/foxair-fake-adb"))
LAB_ROOT = Path(os.environ.get("FOXAIR_QEMU_LAB_ROOT", "/opt/phnix-lab"))
ROOTFS = Path(os.environ.get("FOXAIR_QEMU_LAB_ROOTFS", str(LAB_ROOT / "rootfs")))
DEBUG_STATE = Path(os.environ.get("FOXAIR_DEBUG_STREAM_STATE", str(STATE_DIR / "debug-stream.state")))

SCENARIOS = (
    ("success", "Erfolg - schnell"),
    ("success-real-timing", "Erfolg - reales V3.4-Timing"),
    ("same-version", "Gleiche Version"),
    ("stall-c350", "Keine Antwort auf C350"),
    ("stall-c5a8", "Keine Block-ACKs"),
    ("restart-at-50-resume", "Neustart bei 50 Prozent / Resume"),
    ("resume-fast", "Resume - 40 + 40 Sekunden"),
    ("resume-original", "Resume - originale Wartezeit"),
)


def run(*args: str, timeout: int = 45) -> tuple[int, str]:
    proc = subprocess.run(
        [str(CONTROL), *args], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=timeout, check=False,
    )
    return proc.returncode, proc.stdout.strip()


def backend_status() -> tuple[dict, str]:
    proc = subprocess.run(
        ["python3", str(ADAPTER), "status"], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8, check=False,
    )
    if proc.returncode:
        return {}, (proc.stderr or proc.stdout).strip()
    try:
        return json.loads(proc.stdout), ""
    except json.JSONDecodeError as exc:
        return {}, f"Status ist kein gueltiges JSON: {exc}"


def newest_run_status() -> dict:
    runs = ROOTFS / "data/foxair_ota_runner/runs"
    candidates = list(runs.glob("*/status.json")) if runs.is_dir() else []
    if not candidates:
        return {}
    newest = max(candidates, key=lambda path: path.stat().st_mtime)
    try:
        result = json.loads(newest.read_text(encoding="utf-8"))
        result["_path"] = str(newest)
        lock = runs.parent / "active.lock"
        active = False
        try:
            pid = int((lock / "pid").read_text(encoding="ascii").strip())
            run_id = (lock / "run_id").read_text(encoding="ascii").strip()
            os.kill(pid, 0)
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
            active = (run_id == str(result.get("run_id", ""))
                      and b"dtu_ota_supervisor" in cmdline)
        except (OSError, ValueError):
            pass
        result["_active"] = active
        return result
    except (OSError, json.JSONDecodeError):
        return {"phase": "Statusdatei unlesbar", "_path": str(newest)}


def service_active(name: str) -> bool:
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", name], check=False
    ).returncode == 0


def modem_log_mode() -> str:
    try:
        return DEBUG_STATE.read_text(encoding="utf-8").strip() or "on"
    except OSError:
        return "on"


def process_count(needle: str) -> int:
    proc = subprocess.run(
        ["ps", "-eo", "args="], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, check=False,
    )
    return sum(needle in line for line in proc.stdout.splitlines())


def format_duration(seconds: object) -> str:
    try:
        total = max(0, int(float(str(seconds))))
    except (TypeError, ValueError):
        return "-"
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def snapshot() -> dict:
    base, error = backend_status()
    ota = newest_run_status()
    pids = base.get("service_pids") or []
    runner_pid = base.get("scenario_runner_pid")
    adb_online = bool(base.get("adb_online"))
    phase = str(ota.get("phase", "-"))
    terminal = bool(ota.get("terminal"))
    recovery = str(ota.get("recovery", "-"))
    if error:
        verdict = "STATUSFEHLER"
        severity = "error"
    elif ota.get("_active") and not terminal and recovery in {"required", "in-progress"}:
        verdict = "RECOVERY NOETIG"
        severity = "error"
    elif ota.get("_active") and not terminal and ota.get("state") in {"running", "prepared"}:
        verdict = "UPDATE LAEUFT"
        severity = "active"
    elif not pids or not runner_pid:
        verdict = "SIMULATOR GESTOPPT"
        severity = "error"
    elif not adb_online:
        verdict = "ADB OFFLINE"
        severity = "warn"
    else:
        verdict = "BEREIT"
        severity = "ok"
    runner = base.get("scenario_runner") or {}
    run_dir = Path(str(runner.get("run_dir", "")))
    scenario_exit = "-"
    if run_dir.is_dir() and (run_dir / "exit-code.txt").is_file():
        try:
            scenario_exit = (run_dir / "exit-code.txt").read_text().strip()
        except OSError:
            scenario_exit = "?"
    ota_elapsed = "-"
    if ota.get("_active") and not terminal and ota.get("started_at"):
        try:
            ota_elapsed = format_duration(time.time() - float(ota["started_at"]))
        except (TypeError, ValueError):
            pass
    return {
        "base": base, "ota": ota, "error": error, "verdict": verdict,
        "severity": severity, "phase": phase, "pids": pids,
        "runner_pid": runner_pid, "adb_online": adb_online,
        "fake_adb": service_active("foxair-fake-adb.service"),
        "debug_service": service_active("foxair-debug-stream.service"),
        "modem_log": modem_log_mode(),
        "httpd_count": process_count("busybox httpd -p 127.0.0.1:8081"),
        "scenario_exit": scenario_exit,
        "runner_started": runner.get("started_at", "-"),
        "run_dir": str(run_dir) if run_dir.is_dir() else "",
        "ota_elapsed": ota_elapsed,
        "refreshed": time.strftime("%H:%M:%S"),
    }


def clipped(text: object, width: int) -> str:
    value = str(text)
    return value if len(value) <= width else value[: max(0, width - 3)] + "..."


def add(stdscr, row: int, col: int, text: object, attr: int = 0) -> None:
    height, width = stdscr.getmaxyx()
    if 0 <= row < height and col < width:
        try:
            stdscr.addstr(row, col, clipped(text, width - col - 1), attr)
        except curses.error:
            pass


def choose(stdscr, title: str, options: list[tuple[str, str]]) -> str | None:
    stdscr.timeout(-1)
    index = 0
    while True:
        stdscr.erase()
        add(stdscr, 0, 0, title, curses.A_BOLD)
        add(stdscr, 1, 0, "Pfeile: Auswahl  Enter: ausfuehren  Esc: zurueck")
        for pos, (value, label) in enumerate(options):
            marker = "> " if pos == index else "  "
            attr = curses.color_pair(4) | curses.A_BOLD if pos == index else 0
            add(stdscr, 3 + pos, 1, f"{marker}{label}  [{value}]", attr)
        stdscr.refresh()
        key = stdscr.getch()
        if key in (27, ord("q")):
            return None
        if key in (curses.KEY_UP, ord("k")):
            index = (index - 1) % len(options)
        elif key in (curses.KEY_DOWN, ord("j")):
            index = (index + 1) % len(options)
        elif key in (10, 13, curses.KEY_ENTER):
            return options[index][0]


def prompt(stdscr, title: str, default: str = "") -> str | None:
    stdscr.timeout(-1)
    curses.echo()
    curses.curs_set(1)
    try:
        stdscr.erase()
        add(stdscr, 0, 0, title, curses.A_BOLD)
        add(stdscr, 2, 0, f"Wert [{default}]: ")
        stdscr.refresh()
        raw = stdscr.getstr(2, len(f"Wert [{default}]: "), 40).decode("utf-8").strip()
        return raw or default
    except (curses.error, UnicodeDecodeError):
        return None
    finally:
        curses.noecho()
        curses.curs_set(0)


def confirm(stdscr, question: str) -> bool:
    stdscr.timeout(-1)
    stdscr.erase()
    add(stdscr, 0, 0, question, curses.A_BOLD | curses.color_pair(3))
    add(stdscr, 2, 0, "Mit J bestaetigen, jede andere Taste bricht ab.")
    stdscr.refresh()
    return stdscr.getch() in (ord("j"), ord("J"), ord("y"), ord("Y"))


def result_screen(stdscr, title: str, code: int, output: str) -> None:
    stdscr.timeout(-1)
    stdscr.erase()
    attr = curses.color_pair(2 if code == 0 else 1) | curses.A_BOLD
    add(stdscr, 0, 0, f"{title}: {'OK' if code == 0 else 'FEHLER'}", attr)
    for row, line in enumerate((output or "(keine Ausgabe)").splitlines(), 2):
        add(stdscr, row, 0, line)
    add(stdscr, min(stdscr.getmaxyx()[0] - 1, row + 2 if 'row' in locals() else 3), 0, "Taste druecken ...")
    stdscr.refresh()
    stdscr.getch()


def log_screen(stdscr) -> None:
    base, _ = backend_status()
    runner = base.get("scenario_runner") or {}
    run_dir_value = str(runner.get("run_dir", ""))
    run_dir = Path(run_dir_value) if run_dir_value else None
    ota = newest_run_status()
    ota_path_value = str(ota.get("_path", ""))
    ota_dir = Path(ota_path_value).parent if ota_path_value else None
    options = []
    if run_dir:
        options.extend([
            (str(run_dir / "stdout.log"), "PHNIX-Live-Ausgabe"),
            (str(run_dir / "ttyHSL2-transcript.txt"), "RS485-/Mainboard-Protokoll"),
            (str(run_dir / "qemu-strace.log"), "QEMU-Systemaufrufe (technisch)"),
        ])
    if ota_dir:
        options.extend([
            (str(ota_dir / "hook.log"), "OTA-Hook-Protokoll"),
            (str(ota_dir / "launcher.log"), "OTA-Launcher-Protokoll"),
        ])
    options.extend([
        (str(STATE_DIR / "qemu-adb/scenario-lab.out"), "Launcher-Log (nur Startfehler; oft leer)"),
        ("journal:foxair-fake-adb.service", "Fake-ADB-Dienst"),
        ("journal:foxair-debug-stream.service", "Debugstream-Dienst"),
    ])
    target = choose(stdscr, "Log auswaehlen", options)
    if not target:
        return
    stdscr.timeout(1000)
    while True:
        max_lines = max(1, stdscr.getmaxyx()[0] - 3)
        if target.startswith("journal:"):
            proc = subprocess.run(
                ["journalctl", "-u", target.split(":", 1)[1], "-n", str(max_lines), "--no-pager"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            content = proc.stdout
        else:
            proc = subprocess.run(
                ["tail", "-n", str(max_lines), target], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            content = proc.stdout
        lines = content.splitlines()[-max_lines:] or ["(Log ist derzeit leer)"]
        stdscr.erase()
        add(stdscr, 0, 0, "Log (Auto 1s, Esc/Q: zurueck)", curses.A_BOLD)
        for row, line in enumerate(lines, 1):
            add(stdscr, row, 0, line)
        stdscr.refresh()
        key = stdscr.getch()
        if key in (27, ord("q"), ord("Q")):
            return


def draw(stdscr, state: dict, message: str) -> None:
    stdscr.erase()
    base, ota = state["base"], state["ota"]
    scenario = base.get("scenario") or {}
    color = {"ok": 2, "warn": 3, "error": 1, "active": 4}[state["severity"]]
    add(stdscr, 0, 0, "FoxAir OTA Simulator", curses.A_BOLD)
    add(stdscr, 0, 27, state["verdict"], curses.color_pair(color) | curses.A_BOLD)
    add(stdscr, 0, 55, f"Auto 2s | {state['refreshed']}")
    add(stdscr, 2, 0, f"Szenario:       {scenario.get('scenario', '-')}")
    add(stdscr, 3, 0, f"Board-Version:  {scenario.get('board_version', '-')}")
    add(stdscr, 4, 0, f"PHNIX-PID(s):   {', '.join(map(str, state['pids'])) or '-'}")
    add(stdscr, 5, 0, f"Szenario-PID:   {state['runner_pid'] or '-'}")
    add(stdscr, 6, 0, f"ADB / Debug:    {'online' if state['adb_online'] else 'offline'} / {state['modem_log']}")
    add(stdscr, 7, 0, f"Dienste:        ADB={'OK' if state['fake_adb'] else 'FEHLER'}  Debug={'OK' if state['debug_service'] else 'FEHLER'}")
    add(stdscr, 8, 0, f"HTTP-Server:    {state['httpd_count']}   QEMU-Exit: {state['scenario_exit']}   Start: {state['runner_started']}", curses.color_pair(3) if state["httpd_count"] > 1 else 0)
    run_label = "Aktiver OTA-Lauf" if ota.get("_active") else "Letzter OTA-Lauf (inaktiv)"
    add(stdscr, 10, 0, run_label, curses.A_BOLD)
    add(stdscr, 11, 0, f"ID:             {ota.get('run_id', '-')}   Laufzeit: {state.get('ota_elapsed', '-')}")
    add(stdscr, 12, 0, f"Phase:          {state['phase']}")
    add(stdscr, 13, 0, f"Fortschritt:    {ota.get('progress', 0)} %   Offset {ota.get('offset', 0)} / {ota.get('length', 0)}")
    add(stdscr, 14, 0, f"C350/C357/C5A8: {ota.get('c350_sent', False)} / {ota.get('c357_sent', False)} / {ota.get('c5a8_sent', False)}")
    add(stdscr, 15, 0, f"Recovery:       {ota.get('recovery', '-')}   Abbruch erlaubt: {ota.get('abort_allowed', '-')}")
    add(stdscr, 16, 0, f"Grund:          {ota.get('reason', '-')}")
    height, width = stdscr.getmaxyx()
    detail = str(ota.get("detail", "-") or "-")
    detail_lines = textwrap.wrap(detail, width=max(10, width - 17)) or ["-"]
    if len(detail_lines) > 2:
        detail_lines = [detail_lines[0], clipped(detail_lines[1], max(4, width - 20)) + "..."]
    add(stdscr, 17, 0, f"Detail:         {detail_lines[0]}")
    if len(detail_lines) > 1:
        add(stdscr, 18, 17, detail_lines[1])
    if state["error"]:
        add(stdscr, 19, 0, state["error"], curses.color_pair(1))
    add(stdscr, 20, 0, "[R] Status  [S] Szenario  [B] Board-Version  [X] Reset  [F] Reparieren", curses.A_BOLD)
    add(stdscr, 21, 0, "[C] Dienst-Crash  [M] Modem-Log  [A] ADB an/aus  [L] Logs  [Q] Ende", curses.A_BOLD)
    if message:
        add(stdscr, min(22, height - 1), 0, message, curses.color_pair(4))
    stdscr.refresh()


def main(stdscr) -> None:
    curses.curs_set(0)
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_RED, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_CYAN, -1)
    stdscr.keypad(True)
    message = ""
    while True:
        try:
            state = snapshot()
        except Exception as exc:  # keep the recovery UI usable
            state = {"base": {}, "ota": {}, "error": str(exc), "verdict": "STATUSFEHLER", "severity": "error", "phase": "-", "pids": [], "runner_pid": None, "adb_online": False, "fake_adb": False, "debug_service": False, "modem_log": "?", "httpd_count": 0, "scenario_exit": "-", "runner_started": "-", "ota_elapsed": "-", "refreshed": time.strftime("%H:%M:%S")}
        draw(stdscr, state, message)
        message = ""
        stdscr.timeout(2000)
        key = stdscr.getch()
        if key == -1:
            continue
        if key in (ord("q"), ord("Q")):
            return
        if key in (ord("r"), ord("R")):
            continue
        if key in (ord("s"), ord("S")):
            value = choose(stdscr, "Szenario auswaehlen (startet den Runner neu)", list(SCENARIOS))
            if value and confirm(stdscr, f"Szenario '{value}' jetzt starten?"):
                code, output = run("scenario", value, timeout=90)
                result_screen(stdscr, "Szenario", code, output)
        elif key in (ord("b"), ord("B")):
            value = prompt(stdscr, "Board-Version setzen (vier Ziffern)", str((state["base"].get("scenario") or {}).get("board_version", "0033")))
            if value:
                code, output = run("board-version", value, timeout=90)
                result_screen(stdscr, "Board-Version", code, output)
        elif key in (ord("x"), ord("X")):
            value = choose(stdscr, "Reset-Szenario auswaehlen", list(SCENARIOS))
            if value and confirm(stdscr, f"Laufzustand loeschen und '{value}' neu starten?"):
                code, output = run("reset", value, timeout=120)
                result_screen(stdscr, "Reset", code, output)
        elif key in (ord("f"), ord("F")):
            current = str((state["base"].get("scenario") or {}).get("scenario", "success"))
            if confirm(stdscr, f"Altzustand bereinigen und '{current}' sauber neu starten?"):
                code, output = run("reset", current, timeout=120)
                result_screen(stdscr, "Simulator-Reparatur", code, output)
        elif key in (ord("c"), ord("C")):
            if confirm(stdscr, "Simulierten PHNIX-Dienst jetzt absichtlich crashen?"):
                code, output = run("service-crash")
                result_screen(stdscr, "Dienst-Crash", code, output)
        elif key in (ord("m"), ord("M")):
            new_mode = "off" if state["modem_log"] == "on" else "on"
            code, output = run("modem-log", new_mode)
            result_screen(stdscr, "Modem-Log", code, output)
        elif key in (ord("a"), ord("A")):
            action = "offline" if state["adb_online"] else "online"
            if confirm(stdscr, f"ADB jetzt {action} schalten? OTA/QEMU laufen weiter."):
                code, output = run(action)
                result_screen(stdscr, "ADB", code, output)
        elif key in (ord("l"), ord("L")):
            log_screen(stdscr)


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("Bitte mit sudo starten: sudo foxair-fake-adbctl ui")
    curses.wrapper(main)
