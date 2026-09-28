#!/usr/bin/env bash
set -Eeuo pipefail

ADB_SERVICE="foxair-adb-remote.service"
DEBUG_SERVICE="foxair-debug-stream.service"
SERVICES=("$ADB_SERVICE" "$DEBUG_SERVICE")
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEBUG_TOOL="$ROOT_DIR/updater/linux/remote_debug_stream.py"

die() { printf '[FEHLER] %s\n' "$*" >&2; exit 1; }
ok() { printf '[OK] %s\n' "$*"; }

require_systemd() {
    command -v systemctl >/dev/null 2>&1 || die "systemctl wurde nicht gefunden"
    systemctl cat "$ADB_SERVICE" >/dev/null 2>&1 \
        || die "$ADB_SERVICE ist nicht installiert. Bitte updater/linux/install.sh erneut ausführen."
    systemctl cat "$DEBUG_SERVICE" >/dev/null 2>&1 \
        || die "$DEBUG_SERVICE ist nicht installiert. Bitte updater/linux/install.sh erneut ausführen."
}

show_status() {
    local adb_state debug_state tty
    adb_state="$(systemctl is-active "$ADB_SERVICE" 2>/dev/null || true)"
    debug_state="$(systemctl is-active "$DEBUG_SERVICE" 2>/dev/null || true)"
    printf 'Remote ADB  TCP 5038: %s\n' "${adb_state:-unknown}"
    printf 'PHNIX Debug TCP 5039: %s\n' "${debug_state:-unknown}"
    if [[ -f "$DEBUG_TOOL" ]]; then
        tty="$(python3 "$DEBUG_TOOL" --detect 2>/dev/null || true)"
        if [[ "$tty" == /dev/* ]]; then
            printf 'PHNIX Debug-Port:      %s\n' "$tty"
        else
            printf 'PHNIX Debug-Port:      nicht erkannt\n'
        fi
    fi
    if command -v ss >/dev/null 2>&1; then
        printf '\nListener:\n'
        ss -ltn 2>/dev/null | awk 'NR==1 || $4 ~ /:5038$/ || $4 ~ /:5039$/'
    fi
}

require_systemd
action="${1:-status}"
case "$action" in
    start)
        sudo systemctl start "${SERVICES[@]}"
        ok "Remotezugriff gestartet: ADB TCP 5038, PHNIX-Debug TCP 5039"
        ;;
    stop)
        sudo systemctl stop "${SERVICES[@]}"
        ok "Remotezugriff gestoppt"
        ;;
    restart)
        sudo systemctl restart "${SERVICES[@]}"
        ok "Remotezugriff neu gestartet"
        ;;
    enable)
        sudo systemctl enable --now "${SERVICES[@]}"
        ok "Remotezugriff aktiviert und gestartet"
        ;;
    disable)
        sudo systemctl disable --now "${SERVICES[@]}"
        ok "Remotezugriff deaktiviert und gestoppt"
        ;;
    status)
        show_status
        ;;
    *)
        die "Verwendung: ./foxair-updater remote {start|stop|restart|status|enable|disable}"
        ;;
esac
