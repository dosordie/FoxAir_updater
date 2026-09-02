#!/usr/bin/env python3
"""Adapter between the fake ADB server and the existing PHNIX QEMU lab.

The ADB protocol implementation lives in ``foxair_fake_adb_server.py``. This
module deliberately does *not* create a second modem simulation. Device paths
such as /data and /cache are mapped directly into the existing QEMU rootfs,
normally ``/opt/phnix-lab/rootfs``.

The original ARM ``/data/phnixIot4G`` process is discovered from /proc. Shell
commands are either handled explicitly on the host side (process identity and a
few Linux status probes) or, for commands required by the updater, executed by
the ARM /bin/sh through qemu-arm-static inside the same rootfs.

Scenario changes are forwarded to the QEMU/Mainboard emulator through an
existing lab control hook/socket when one can be discovered. A JSON control
file is always written as the stable hand-off format. We intentionally do not
pretend that a scenario was applied when no emulator control endpoint exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_LAB_ROOT = Path(os.environ.get("FOXAIR_QEMU_LAB_ROOT", "/opt/phnix-lab"))
DEFAULT_STATE_ROOT = Path(os.environ.get("FOXAIR_FAKE_ADB_STATE", "/var/lib/foxair-fake-adb"))
EXPECTED_SERVICE_SHA256 = "7c573431f0a67620d473419644a83a4f4dc04b8a91bde5923c74a63ba1eaedb7"

MAIN_SCENARIOS = {
    "success",
    "success-real-timing",
    "parser-rejected",
    "crc-error",
    "metadata-mismatch",
    "offset-backwards",
    "offset-overflow",
    "stall-c350",
    "stall-c5a8",
    "helper-exit",
    "success-without-step12",
    "same-version",
    "restart-at-50-resume",
}
CANCEL_SCENARIOS = {"success", "retry-success", "no-response", "rejected", "wrong-ssid", "c36c-only"}
HANDSHAKE_SCENARIOS = {
    "success",
    "wrong-status-1",
    "missing-status-2",
    "metadata-change",
    "c5a8-leak",
    "cancel-fail",
}
SAME_VERSION_SCENARIOS = {"success", "status-1", "c357-leak", "c5a8-leak", "restore-mismatch"}


def lab_root() -> Path:
    return Path(os.environ.get("FOXAIR_QEMU_LAB_ROOT", str(DEFAULT_LAB_ROOT)))


def state_root() -> Path:
    return Path(os.environ.get("FOXAIR_FAKE_ADB_STATE", str(DEFAULT_STATE_ROOT)))


def discover_rootfs() -> Path:
    explicit = os.environ.get("FOXAIR_QEMU_LAB_ROOTFS")
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    root = lab_root()
    candidates.extend((root / "rootfs", root / "root", root / "chroot"))
    for candidate in candidates:
        if (candidate / "data/phnixIot4G").is_file():
            return candidate.resolve()
    if root.is_dir():
        for service in root.glob("*/data/phnixIot4G"):
            if service.is_file():
                return service.parents[1].resolve()
    checked = ", ".join(str(path) for path in candidates)
    raise RuntimeError(
        "PHNIX-QEMU-RootFS nicht gefunden. Erwartet wurde /data/phnixIot4G unter: " + checked
    )


def qemu_rootfs() -> Path:
    return discover_rootfs()


def sim_home() -> Path:
    """Small ADB/control state directory; never the emulated device filesystem."""
    return state_root() / "qemu-adb"


def root_path(remote: str) -> Path:
    if not remote.startswith("/"):
        raise ValueError("Nur absolute Remote-Pfade werden unterstützt")
    root = qemu_rootfs()
    if remote == "/":
        return root
    relative = Path(remote.lstrip("/"))
    candidate = root / relative
    # Resolve only the parent, so a not-yet-existing upload target stays valid.
    parent = candidate.parent.resolve()
    if parent != root and root not in parent.parents:
        raise ValueError("Remote-Pfad verlässt das QEMU-RootFS")
    return candidate


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def _scenario_state_path() -> Path:
    return state_root() / "qemu-scenario.json"


def _lab_control_path() -> Path:
    return Path(
        os.environ.get(
            "FOXAIR_QEMU_SCENARIO_FILE",
            str(lab_root() / "control/foxair-ota-scenario.json"),
        )
    )


def scenario_state() -> dict:
    defaults = {
        "scenario": "success",
        "board_version": "0033",
        "cancel_scenario": "success",
        "handshake_scenario": "success",
        "same_version_scenario": "success",
    }
    path = _scenario_state_path()
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                defaults.update({key: value[key] for key in defaults if isinstance(value.get(key), str)})
        except (OSError, json.JSONDecodeError):
            pass
    return defaults


def _write_scenario_state(value: dict) -> None:
    _atomic_json(_scenario_state_path(), value)
    control = dict(value)
    control.update(
        {
            "schema": "foxair-qemu-ota-scenario-v1",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "rootfs": str(qemu_rootfs()),
        }
    )
    _atomic_json(_lab_control_path(), control)


def _candidate_hooks() -> list[Path]:
    explicit = os.environ.get("FOXAIR_QEMU_SCENARIO_HOOK")
    result: list[Path] = [Path(explicit)] if explicit else []
    tools = lab_root() / "tools"
    for name in (
        "foxair-scenarioctl",
        "phnix-scenarioctl",
        "mainboard-simctl",
        "board-simctl",
        "phnix-labctl",
        "foxair-labctl",
        "labctl",
    ):
        result.append(tools / name)
    if tools.is_dir():
        result.extend(sorted(tools.glob("*scenario*ctl*")))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in result:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_file() and os.access(path, os.X_OK):
            unique.append(path)
    return unique


def scenario_hook() -> Path | None:
    hooks = _candidate_hooks()
    return hooks[0] if hooks else None


def scenario_socket() -> Path | None:
    explicit = os.environ.get("FOXAIR_QEMU_SCENARIO_SOCKET")
    candidates = [Path(explicit)] if explicit else []
    run = lab_root() / "run"
    candidates.extend((run / "scenario.sock", run / "control.sock", run / "mainboard.sock"))
    for path in candidates:
        try:
            if path.exists() and path.is_socket():
                return path
        except OSError:
            continue
    return None


def _send_scenario_socket(path: Path, kind: str, value: str, state: dict) -> tuple[bool, str]:
    payload = json.dumps({"command": kind, "value": value, "state": state}) + "\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2.0)
            client.connect(str(path))
            client.sendall(payload.encode("utf-8"))
            try:
                reply = client.recv(4096).decode("utf-8", errors="replace").strip()
            except socket.timeout:
                reply = ""
    except OSError as exc:
        return False, f"Scenario-Socket fehlgeschlagen: {exc}"
    if reply:
        try:
            parsed = json.loads(reply)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and parsed.get("ok") is False:
            return False, reply
    return True, reply or f"über Socket {path} angewendet"


def apply_control(kind: str, value: str) -> tuple[bool, str]:
    key_for_kind = {
        "board-version": "board_version",
        "scenario": "scenario",
        "cancel-scenario": "cancel_scenario",
        "handshake-scenario": "handshake_scenario",
        "same-version-scenario": "same_version_scenario",
    }
    allowed_for_kind = {
        "scenario": MAIN_SCENARIOS,
        "cancel-scenario": CANCEL_SCENARIOS,
        "handshake-scenario": HANDSHAKE_SCENARIOS,
        "same-version-scenario": SAME_VERSION_SCENARIOS,
    }
    if kind == "board-version":
        if re.fullmatch(r"\d{4}", value) is None:
            return False, "board-version muss genau vier Ziffern enthalten"
        state = scenario_state()
        state["board_version"] = value
        _write_scenario_state(state)
        return True, f"simulierte Mainboard-Version auf {value} gesetzt"
    if kind not in key_for_kind:
        return False, f"Unbekannte Scenario-Art: {kind}"
    if value not in allowed_for_kind[kind]:
        return False, f"Unbekanntes {kind}: {value}"

    state = scenario_state()
    state[key_for_kind[kind]] = value
    _write_scenario_state(state)

    sock = scenario_socket()
    if sock is not None:
        return _send_scenario_socket(sock, kind, value, state)

    hook = scenario_hook()
    if hook is not None:
        env = os.environ.copy()
        env["FOXAIR_QEMU_LAB_ROOT"] = str(lab_root())
        env["FOXAIR_QEMU_LAB_ROOTFS"] = str(qemu_rootfs())
        env["FOXAIR_QEMU_SCENARIO_FILE"] = str(_lab_control_path())
        completed = subprocess.run(
            [str(hook), kind, value],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            timeout=15,
            check=False,
        )
        output = completed.stdout.strip()
        if completed.returncode != 0:
            return False, output or f"Scenario-Hook Exit {completed.returncode}: {hook}"
        return True, output or f"über Hook {hook} angewendet"

    return (
        False,
        "Scenario gespeichert, aber kein QEMU/Mainboard-Control-Hook gefunden. "
        f"Control-Datei: {_lab_control_path()}. "
        "FOXAIR_QEMU_SCENARIO_HOOK oder FOXAIR_QEMU_SCENARIO_SOCKET konfigurieren.",
    )


def reset_state(scenario: str = "success", cancel_scenario: str = "success", *_args) -> None:
    """Reset only the fake-ADB/control markers; never rebuild/delete the QEMU rootfs."""
    qemu_rootfs()  # fail early if the Work lab is not present
    home = sim_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "started").touch()
    state = {
        "scenario": scenario if scenario in MAIN_SCENARIOS else "success",
        "board_version": "0033",
        "cancel_scenario": cancel_scenario if cancel_scenario in CANCEL_SCENARIOS else "success",
        "handshake_scenario": "success",
        "same_version_scenario": "success",
    }
    _write_scenario_state(state)


def _fake_pid_override() -> list[int]:
    value = os.environ.get("FOXAIR_QEMU_FAKE_PID", "").strip()
    if not value:
        return []
    result: list[int] = []
    for item in re.split(r"[ ,]+", value):
        try:
            result.append(int(item))
        except ValueError:
            pass
    return result


def service_pids() -> list[int]:
    override = _fake_pid_override()
    if override:
        return override
    result: list[int] = []
    proc = Path("/proc")
    if not proc.is_dir():
        return result
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = [
                item.decode(errors="replace")
                for item in (entry / "cmdline").read_bytes().split(b"\0")
                if item
            ]
        except OSError:
            continue
        # Wrapper processes (unshare/bash/timeout) contain the complete runner
        # script in their command line and therefore also mention qemu and
        # phnixIot4G.  Android pidof reports only the actual service process;
        # mirror that contract by requiring qemu as argv[0].
        executable = Path(argv[0]).name if argv else ""
        if (
            executable in {"qemu-arm", "qemu-arm-static"}
            and any(arg.startswith("/data/phnixIot4G") for arg in argv[1:])
        ):
            result.append(int(entry.name))
    return sorted(result)


def _service_pid_text() -> bytes:
    pids = service_pids()
    return ((" ".join(str(pid) for pid in pids) + "\n") if pids else "").encode()


def _hash_remote(remote: str, algorithm: str) -> tuple[int, bytes]:
    path = root_path(remote)
    if not path.is_file():
        return 1, b""
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return 0, (digest.hexdigest() + "\n").encode("ascii")


def _qemu_shell_binary() -> tuple[Path, str] | None:
    root = qemu_rootfs()
    for relative in ("usr/bin/qemu-arm-static", "usr/bin/qemu-arm"):
        candidate = root / relative
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate, "/" + relative
    host = shutil.which("qemu-arm-static") or shutil.which("qemu-arm")
    if host:
        return Path(host), host
    return None


def _run_rootfs_shell(command: str) -> tuple[int, bytes]:
    """Run the same shell command inside the ARM QEMU rootfs.

    This mirrors a root ADB shell and is only appropriate for the isolated test
    VM. systemd confines the service and the fake ADB port itself remains
    explicitly documented as unauthenticated lab-only access.
    """
    root = qemu_rootfs()
    qemu = _qemu_shell_binary()
    if qemu is None or not (root / "bin/sh").exists():
        return 127, b"QEMU-/bin/sh im PHNIX-Lab nicht verfuegbar\n"
    _host_qemu, guest_qemu = qemu
    argv = ["chroot", str(root)]
    if guest_qemu.startswith("/") and (root / guest_qemu.lstrip("/")).is_file():
        argv.extend([guest_qemu, "-L", "/", "/bin/sh", "-c", command])
    else:
        # Host qemu cannot be reached after chroot. This branch is diagnostic;
        # the Work lab normally carries /usr/bin/qemu-arm-static.
        return 127, b"qemu-arm-static fehlt im QEMU-RootFS\n"
    completed = subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=20,
        check=False,
    )
    return completed.returncode, completed.stdout


def _pid_state(pid: int) -> str:
    if _fake_pid_override():
        return "State:\tS (sleeping)\nTracerPid:\t0\n"
    try:
        text = Path(f"/proc/{pid}/status").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    wanted = [line for line in text.splitlines() if line.startswith(("State:", "TracerPid:"))]
    return "\n".join(wanted) + ("\n" if wanted else "")


def _signal_service(sig: int) -> bool:
    pids = service_pids()
    if not pids or _fake_pid_override():
        return bool(pids)
    ok = True
    for pid in pids:
        try:
            os.kill(pid, sig)
        except OSError:
            ok = False
    return ok


def shell(command: str) -> tuple[int, bytes]:
    command = command.strip()

    if command in {"pidof phnixIot4G || true", "pidof phnixIot4G"}:
        return 0, _service_pid_text()

    if command.startswith("p=$(pidof phnixIot4G") and "readlink /proc/$p/exe" in command:
        return (0, b"/data/phnixIot4G\n") if service_pids() else (0, b"")

    if command.startswith("p=$(pidof phnixIot4G") and "TracerPid" in command:
        pids = service_pids()
        return (0, _pid_state(pids[0]).encode()) if pids else (0, b"")

    match = re.fullmatch(r"cat ['\"]?(?P<path>/\S+?)['\"]?", command)
    if match:
        path = root_path(match.group("path"))
        return (0, path.read_bytes()) if path.is_file() else (1, b"")

    match = re.search(r"(?P<algo>sha256sum|md5sum) ['\"]?(?P<path>/[^ |'\"]+)['\"]?", command)
    if match and "awk" in command:
        return _hash_remote(match.group("path"), "sha256" if match.group("algo") == "sha256sum" else "md5")

    if command.startswith("ps | awk") and "{helloworld}" in command:
        # The QEMU lab does not need the production watchdog binaries. Preserve
        # the production preflight contract while keeping the real ARM service.
        return 0, b"4001\n4002\n"

    if re.match(r"netstat -(?:nt|tn)\b", command) and ":1883" in command:
        # Network is intentionally isolated in the Work lab. The controller only
        # uses this as proof that the original service was restored.
        return (0, b"tcp 0 0 10.0.0.2:45100 127.0.0.1:1883 ESTABLISHED\n") if service_pids() else (0, b"")

    if command == "pidof gdbserver gdb || true":
        pids: list[str] = []
        proc = Path("/proc")
        if proc.is_dir():
            for name in ("gdbserver", "gdb"):
                for pid_dir in proc.glob("[0-9]*"):
                    try:
                        comm = (pid_dir / "comm").read_text().strip()
                    except OSError:
                        continue
                    if comm == name:
                        pids.append(pid_dir.name)
        return 0, ((" ".join(pids) + "\n") if pids else "").encode()

    match = re.fullmatch(r"kill -(STOP|CONT|TERM|KILL)\s+([0-9]+)", command)
    if match:
        pid = int(match.group(2))
        if pid not in service_pids():
            return 1, b"refusing to signal non-phnix QEMU pid\n"
        sig = getattr(signal, "SIG" + match.group(1))
        if _fake_pid_override():
            return 0, b""
        try:
            os.kill(pid, sig)
        except OSError as exc:
            return 1, (str(exc) + "\n").encode()
        return 0, b""

    if command.startswith("killall") and "phnixIot4G" in command:
        sig = signal.SIGKILL if "-9" in command else signal.SIGTERM
        return (0, b"") if _signal_service(sig) else (1, b"")

    # Everything else is executed inside the same ARM rootfs used by the Work
    # lab. This includes file probes, df, busybox, chmod, runtime-hook commands
    # and other normal updater shell operations.
    return _run_rootfs_shell(command)


def service_info() -> dict:
    root = qemu_rootfs()
    service = root / "data/phnixIot4G"
    digest = None
    if service.is_file():
        digest_obj = hashlib.sha256()
        with service.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest_obj.update(chunk)
        digest = digest_obj.hexdigest()
    hook = scenario_hook()
    sock = scenario_socket()
    return {
        "backend": "qemu-rootfs",
        "lab_root": str(lab_root()),
        "rootfs": str(root),
        "service": str(service),
        "service_size": service.stat().st_size if service.is_file() else None,
        "service_sha256": digest,
        "service_sha256_expected": EXPECTED_SERVICE_SHA256,
        "service_hash_matches_verified_build": digest == EXPECTED_SERVICE_SHA256,
        "service_pids": service_pids(),
        "adb_online": (sim_home() / "started").exists(),
        "scenario": scenario_state(),
        "scenario_file": str(_lab_control_path()),
        "scenario_hook": str(hook) if hook else None,
        "scenario_socket": str(sock) if sock else None,
    }


def _set_online(value: bool) -> None:
    sim_home().mkdir(parents=True, exist_ok=True)
    marker = sim_home() / "started"
    if value:
        marker.touch()
    else:
        marker.unlink(missing_ok=True)


def _print_status() -> None:
    print(json.dumps(service_info(), indent=2, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="FoxAir QEMU-lab adapter/control")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("online")
    sub.add_parser("offline")
    reset = sub.add_parser("reset")
    reset.add_argument("scenario", nargs="?", default="success")
    for name in ("scenario", "cancel-scenario", "handshake-scenario", "same-version-scenario"):
        item = sub.add_parser(name)
        item.add_argument("value")
    args = parser.parse_args()

    try:
        if args.command == "status":
            _print_status()
            return 0
        if args.command == "online":
            _set_online(True)
            return 0
        if args.command == "offline":
            _set_online(False)
            return 0
        if args.command == "reset":
            reset_state(args.scenario, "success")
            ok, message = apply_control("scenario", args.scenario)
            print(message)
            return 0 if ok else 3
        if args.command in {"scenario", "cancel-scenario", "handshake-scenario", "same-version-scenario"}:
            ok, message = apply_control(args.command, args.value)
            print(message)
            return 0 if ok else 3
    except Exception as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
