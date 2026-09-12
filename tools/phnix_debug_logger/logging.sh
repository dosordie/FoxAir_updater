#!/usr/bin/env bash
# Passive PHNIX phnixIot4G debug logger for Raspberry Pi OS / Debian.
#
# PHNIX facts used here:
# - phnixIot4G writes its debug output to modem-side /dev/ttyGS0 at 115200 8N1.
# - The Raspberry Pi sees the debug endpoint as USB VID 1e0e / PID 9001 / IF 04.
# - On the Linux USB-serial side the baud rate is not forced: the SimTech USB
#   serial driver may reject a baud-rate change although the endpoint works.
# - A service restart is blocked while PHNIX OTA safety markers are present or
#   cannot be checked reliably.
#
# The script never modifies the phnixIot4G binary or the modem filesystem.

set -u

PROGRAM_NAME=${0##*/}
USB_VENDOR_ID="1e0e"
USB_PRODUCT_ID="9001"
USB_INTERFACE_NUM="04"
SERVICE_NAME="phnixIot4G"
SCAN_INTERVAL=3
RESTART_TIMEOUT=25
HEARTBEAT_INTERVAL=300

DEFAULT_LOG_DIR="${HOME:-.}/FoxAir_Logs"
LOG_DIR="${LOG_DIR:-$DEFAULT_LOG_DIR}"
NO_RESTART=0
ADB_SELECTED_SERIAL=""
LOGGER_PID=""
HEARTBEAT_PID=""
READY_FILE="${TMPDIR:-/tmp}/phnix_debug_logger.$$.${RANDOM}.ready"
PARENT_CLEANED=0

OTA_MARKERS=(
    "/tmp/phnix_ota_hook/run.active"
    "/tmp/phnix_ota_hook/transfer-started"
    "/tmp/phnix_ota_hook/original-service-owns"
)

say()   { printf '%s\n' "$*"; }
warn()  { printf 'WARNUNG: %s\n' "$*" >&2; }
error() { printf 'FEHLER: %s\n' "$*" >&2; }

usage() {
    cat <<EOF_HELP
PHNIX Debug-Dauerlogger

Verwendung:
  ./$PROGRAM_NAME
  ./$PROGRAM_NAME --no-restart
  ./$PROGRAM_NAME --help

Optionen:
  --no-restart   ADB-Verbindung prüfen, phnixIot4G aber NICHT neu starten;
                 serielles Logging läuft trotzdem.
  --help         Diese Hilfe anzeigen.

Umgebungsvariablen:
  LOG_DIR        Zielverzeichnis der Logs (Standard: ~/FoxAir_Logs)
  ADB_SERIAL     ADB-Seriennummer erzwingen, falls mehrere ADB-Geräte verbunden sind.

Der Debugport wird ausschließlich über VID $USB_VENDOR_ID / PID $USB_PRODUCT_ID /
USB-Interface $USB_INTERFACE_NUM ermittelt. Es gibt keine feste /dev/ttyUSBx-Nummer.
Die Host-Baudrate wird bei diesem USB-Serial-Endpunkt absichtlich nicht erzwungen.
EOF_HELP
}

manual_install_help() {
    local packages="$1" apt_cmd="${2:-apt-get}"
    say ""
    say "Manuelle Installation auf Raspberry Pi OS / Debian:"
    if [ "${EUID:-$(id -u)}" -eq 0 ]; then
        printf '  %s update\n  %s install %s\n' "$apt_cmd" "$apt_cmd" "$packages"
    elif command -v sudo >/dev/null 2>&1; then
        printf '  sudo %s update\n  sudo %s install %s\n' "$apt_cmd" "$apt_cmd" "$packages"
    else
        say "  Als root anmelden und ausführen:"
        printf '  %s update\n  %s install %s\n' "$apt_cmd" "$apt_cmd" "$packages"
    fi
}

check_dependencies() {
    local -a missing=() packages=()
    local pair cmd pkg p seen apt_cmd="" answer

    for pair in "adb:adb" "udevadm:udev" "stty:coreutils"; do
        cmd=${pair%%:*}
        pkg=${pair#*:}
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing+=("$cmd")
            seen=0
            for p in "${packages[@]:-}"; do
                [ "$p" = "$pkg" ] && seen=1
            done
            [ "$seen" -eq 1 ] || packages+=("$pkg")
        fi
    done

    [ "${#missing[@]}" -eq 0 ] && return 0

    error "Folgende benötigte Programme fehlen: ${missing[*]}"
    say "Benötigte Debian-Pakete: ${packages[*]}"

    if [ -e /etc/debian_version ]; then
        command -v apt-get >/dev/null 2>&1 && apt_cmd="apt-get"
        [ -n "$apt_cmd" ] || { command -v apt >/dev/null 2>&1 && apt_cmd="apt"; }
    fi
    if [ -z "$apt_cmd" ]; then
        error "Keine unterstützte Debian/Raspberry-Pi-OS-Paketverwaltung erkannt."
        manual_install_help "${packages[*]}"
        return 1
    fi
    if [ "${EUID:-$(id -u)}" -ne 0 ] && ! command -v sudo >/dev/null 2>&1; then
        error "Für automatische Installation wären root-Rechte nötig, aber sudo fehlt."
        manual_install_help "${packages[*]}" "$apt_cmd"
        return 1
    fi

    printf 'Fehlende Pakete automatisch installieren? [j/N] '
    answer=""
    if ! { IFS= read -r answer </dev/tty; } 2>/dev/null; then
        warn "Keine interaktive Konsole verfügbar; automatische Installation wird nicht gestartet."
    fi
    case "$answer" in
        j|J|ja|JA|Ja|y|Y|yes|YES|Yes) ;;
        *)
            say "Keine automatische Installation durchgeführt."
            manual_install_help "${packages[*]}" "$apt_cmd"
            return 1
            ;;
    esac

    say "Installiere ausschließlich die fehlenden Pakete: ${packages[*]}"
    if [ "${EUID:-$(id -u)}" -eq 0 ]; then
        "$apt_cmd" update && "$apt_cmd" install -y "${packages[@]}" || return 1
    else
        sudo "$apt_cmd" update && sudo "$apt_cmd" install -y "${packages[@]}" || return 1
    fi

    for cmd in "${missing[@]}"; do
        command -v "$cmd" >/dev/null 2>&1 || { error "'$cmd' ist weiterhin nicht verfügbar."; return 1; }
    done
}

prepare_log_dir() {
    umask 077
    mkdir -p -- "$LOG_DIR" || { error "Logverzeichnis konnte nicht angelegt werden: $LOG_DIR"; return 1; }
    chmod 700 -- "$LOG_DIR" 2>/dev/null || true
    LOG_DIR=$(cd -- "$LOG_DIR" 2>/dev/null && pwd -P) || return 1
    say "Logverzeichnis: $LOG_DIR"
    warn "PHNIX-Debuglogs können IMEI/ICCID, ProductKey, DeviceSecret und andere Kennungen enthalten."
    warn "Rohlogs vor einer Veröffentlichung immer manuell prüfen."
}

adb_run() {
    if [ -n "$ADB_SELECTED_SERIAL" ]; then
        adb -s "$ADB_SELECTED_SERIAL" "$@"
    else
        adb "$@"
    fi
}
adb_shell() { adb_run shell "$@"; }

print_adb_rows() {
    local row
    say "Gefundene ADB-Geräte:"
    [ "$#" -gt 0 ] || { say "  (keine)"; return; }
    for row in "$@"; do printf '  %s\n' "$row"; done
}

select_adb_device() {
    local output line serial state rest i found=-1
    local -a rows=() serials=() states=()

    adb start-server >/dev/null 2>&1 || { error "ADB-Server konnte nicht gestartet werden."; return 1; }
    output=$(adb devices 2>&1) || { error "'adb devices' ist fehlgeschlagen: $output"; return 1; }

    while IFS= read -r line; do
        line=${line%$'\r'}
        [ -n "$line" ] || continue
        case "$line" in "List of devices attached"*|"* daemon"*) continue ;; esac
        serial=${line%%[[:space:]]*}
        rest=${line#"$serial"}
        rest=${rest#${rest%%[![:space:]]*}}
        state=${rest%%[[:space:]]*}
        [ -n "$serial" ] && [ -n "$state" ] || continue
        rows+=("$serial  [$state]")
        serials+=("$serial")
        states+=("$state")
    done <<< "$output"

    if [ -n "${ADB_SERIAL:-}" ]; then
        for i in "${!serials[@]}"; do
            [ "${serials[$i]}" = "$ADB_SERIAL" ] && { found=$i; break; }
        done
        [ "$found" -ge 0 ] || { error "ADB_SERIAL='$ADB_SERIAL' wurde nicht gefunden."; print_adb_rows "${rows[@]}"; return 1; }
        serial=${serials[$found]}; state=${states[$found]}
    else
        [ "${#serials[@]}" -gt 0 ] || { error "Kein ADB-Gerät gefunden."; return 1; }
        [ "${#serials[@]}" -eq 1 ] || {
            error "Mehrere ADB-Geräte gefunden; aus Sicherheitsgründen wird keines automatisch gewählt."
            print_adb_rows "${rows[@]}"
            say "Bei Bedarf ADB_SERIAL=<Seriennummer> vor dem Start setzen."
            return 1
        }
        serial=${serials[0]}; state=${states[0]}
    fi

    case "$state" in
        device) ADB_SELECTED_SERIAL="$serial"; say "ADB-Verbindung OK: $serial"; return 0 ;;
        unauthorized) error "ADB-Gerät '$serial' ist unauthorized." ;;
        offline) error "ADB-Gerät '$serial' ist offline." ;;
        *) error "ADB-Gerät '$serial' ist nicht bereit (Status: $state)." ;;
    esac
    return 1
}

read_sysfs_usb_info() {
    local tty_name="$1" path vendor="" product="" iface=""
    path=$(readlink -f "/sys/class/tty/$tty_name/device" 2>/dev/null || true)
    while [ -n "$path" ] && [ "$path" != "/" ]; do
        [ -n "$iface" ]   || { [ -r "$path/bInterfaceNumber" ] && IFS= read -r iface < "$path/bInterfaceNumber"; }
        [ -n "$vendor" ]  || { [ -r "$path/idVendor" ] && IFS= read -r vendor < "$path/idVendor"; }
        [ -n "$product" ] || { [ -r "$path/idProduct" ] && IFS= read -r product < "$path/idProduct"; }
        [ -n "$vendor" ] && [ -n "$product" ] && [ -n "$iface" ] && break
        path=${path%/*}; [ -n "$path" ] || path="/"
    done
    printf '%s|%s|%s\n' "${vendor,,}" "${product,,}" "${iface,,}"
}

read_tty_usb_info() {
    local dev="$1" tty_name=${1##*/} props key value
    local vendor="" product="" iface="" sysinfo sv sp si
    props=$(udevadm info --query=property --name="$dev" 2>/dev/null || true)
    while IFS='=' read -r key value; do
        case "$key" in
            ID_VENDOR_ID) vendor=${value,,} ;;
            ID_MODEL_ID) product=${value,,} ;;
            ID_USB_INTERFACE_NUM) iface=${value,,} ;;
        esac
    done <<< "$props"
    if [ -z "$vendor" ] || [ -z "$product" ] || [ -z "$iface" ]; then
        sysinfo=$(read_sysfs_usb_info "$tty_name")
        IFS='|' read -r sv sp si <<< "$sysinfo"
        [ -n "$vendor" ] || vendor=$sv; [ -n "$product" ] || product=$sp; [ -n "$iface" ] || iface=$si
    fi
    printf '%s|%s|%s\n' "$vendor" "$product" "$iface"
}

discover_debug_port() {
    local sys_tty tty_name dev info vendor product iface
    local -a matches=()
    for sys_tty in /sys/class/tty/*; do
        [ -e "$sys_tty" ] || continue
        tty_name=${sys_tty##*/}; dev="/dev/$tty_name"; [ -c "$dev" ] || continue
        info=$(read_tty_usb_info "$dev"); IFS='|' read -r vendor product iface <<< "$info"
        if [ "$vendor" = "$USB_VENDOR_ID" ] && [ "$product" = "$USB_PRODUCT_ID" ] && [ "$iface" = "$USB_INTERFACE_NUM" ]; then
            matches+=("$dev")
        fi
    done
    [ "${#matches[@]}" -eq 1 ] || return 1
    printf '%s\n' "${matches[0]}"
}

print_tty_diagnostics() {
    local sys_tty tty_name dev info vendor product iface found=0
    warn "Kein eindeutiges PHNIX-Debuginterface VID=$USB_VENDOR_ID PID=$USB_PRODUCT_ID IF=$USB_INTERFACE_NUM gefunden."
    for sys_tty in /sys/class/tty/*; do
        [ -e "$sys_tty" ] || continue
        tty_name=${sys_tty##*/}; dev="/dev/$tty_name"; [ -c "$dev" ] || continue
        [[ "$tty_name" == ttyUSB* || "$tty_name" == ttyACM* ]] || continue
        info=$(read_tty_usb_info "$dev"); IFS='|' read -r vendor product iface <<< "$info"
        printf '  %s  VID=%s PID=%s IF=%s\n' "$dev" "${vendor:-?}" "${product:-?}" "${iface:-?}" >&2
        found=1
    done
    [ "$found" -eq 1 ] || warn "Keine ttyUSB/ttyACM-Kandidaten sichtbar."
}

write_log_line() {
    local raw="$1" stamp day logfile
    raw=${raw%$'\r'}
    stamp=$(date '+%Y-%m-%d %H:%M:%S')
    day=${stamp%% *}
    logfile="$LOG_DIR/phnix_$day.log"
    printf '[%s] %s\n' "$stamp" "$raw" >> "$logfile" || { error "Logdatei kann nicht geschrieben werden: $logfile"; return 1; }
}

logger_supervisor() {
    local port="" saved_stty="" line="" attempts=0 fd_open=0 cleaned=1

    worker_cleanup() {
        [ "$cleaned" -eq 0 ] || return 0
        cleaned=1
        [ "$fd_open" -eq 0 ] || { exec 3<&- || true; fd_open=0; }
        if [ -n "$port" ] && [ -n "$saved_stty" ] && [ -c "$port" ]; then
            stty -F "$port" "$saved_stty" >/dev/null 2>&1 || true
        fi
    }
    worker_stop() { worker_cleanup; exit 0; }
    trap worker_stop INT TERM
    trap worker_cleanup EXIT

    while :; do
        port=""
        if port=$(discover_debug_port); then
            attempts=0
        else
            attempts=$((attempts + 1))
            if [ "$attempts" -eq 1 ] || [ $((attempts % 10)) -eq 0 ]; then
                print_tty_diagnostics
                say "Warte auf PHNIX-Debuginterface (erneuter Versuch in ${SCAN_INTERVAL}s) ..."
            fi
            sleep "$SCAN_INTERVAL"
            continue
        fi

        cleaned=0
        saved_stty=$(stty -F "$port" -g 2>/dev/null || true)
        if [ -z "$saved_stty" ]; then
            error "Serielle Einstellungen von $port können nicht gelesen werden (Berechtigung?)."
            cleaned=1; sleep "$SCAN_INTERVAL"; continue
        fi

        # Intentionally no baud-rate argument here. The real PHNIX/SimTech USB
        # serial endpoint accepts the other termios flags but can reject 115200.
        if ! stty -F "$port" cs8 -parenb -cstopb -ixon -ixoff -ixany -crtscts \
            -icanon -echo -echoe -echok -echonl -icrnl -inlcr -igncr -istrip min 1 time 0 2>/dev/null; then
            error "$port konnte nicht für USB-Serial 8N1 ohne Flow-Control konfiguriert werden."
            worker_cleanup; port=""; saved_stty=""; sleep "$SCAN_INTERVAL"; continue
        fi

        if ! exec 3<"$port"; then
            error "$port konnte nicht zum Lesen geöffnet werden."
            worker_cleanup; port=""; saved_stty=""; sleep "$SCAN_INTERVAL"; continue
        fi
        fd_open=1
        say "PHNIX-Debugport verbunden: $port (USB-Serial IF $USB_INTERFACE_NUM, 8N1; Baudrate nicht erzwungen)"
        printf '%s\n' "$port" > "$READY_FILE"

        while :; do
            line=""
            if IFS= read -r line <&3; then
                write_log_line "$line" || return 1
                continue
            fi
            [ -z "$line" ] || write_log_line "$line" || return 1
            break
        done

        warn "PHNIX-Debugport $port wurde getrennt. Suche nach erneutem USB-Connect ..."
        rm -f -- "$READY_FILE"
        worker_cleanup
        port=""; saved_stty=""
        sleep "$SCAN_INTERVAL"
    done
}

wait_for_logger_ready() {
    local port
    while :; do
        if [ -s "$READY_FILE" ]; then
            IFS= read -r port < "$READY_FILE" || port=""
            [ -n "$port" ] && return 0
        fi
        if [ -n "$LOGGER_PID" ] && ! kill -0 "$LOGGER_PID" 2>/dev/null; then
            error "Logger-Prozess wurde unerwartet beendet."
            return 1
        fi
        sleep 1
    done
}

check_ota_restart_safety() {
    local marker output state
    for marker in "${OTA_MARKERS[@]}"; do
        output=$(adb_shell "if [ -e '$marker' ]; then echo PRESENT; else echo ABSENT; fi" 2>&1) || {
            warn "OTA-Schutzmarker konnte nicht sicher geprüft werden: $marker"; return 1;
        }
        state=${output%$'\r'}; state=${state##*$'\n'}
        case "$state" in
            ABSENT) ;;
            PRESENT) warn "OTA-Schutzmarker ist vorhanden: $marker"; return 1 ;;
            *) warn "Unerwartete Antwort beim Prüfen von $marker: ${output:-<leer>}"; return 1 ;;
        esac
    done
}

restart_phnix_service_once() {
    local output old_pid current pid deadline new_pid=""
    local -a old_pids=()

    if ! check_ota_restart_safety; then
        warn "$SERVICE_NAME wird NICHT neu gestartet; passives Logging läuft weiter."
        return 1
    fi
    output=$(adb_shell "pidof $SERVICE_NAME" 2>&1) || { warn "$SERVICE_NAME-PID konnte nicht ermittelt werden; kein Neustart."; return 1; }
    read -r -a old_pids <<< "${output//$'\r'/}"
    if [ "${#old_pids[@]}" -ne 1 ] || ! [[ "${old_pids[0]}" =~ ^[0-9]+$ ]]; then
        warn "Keine eindeutige $SERVICE_NAME-PID gefunden (${output:-<leer>}); kein Neustart."
        return 1
    fi
    old_pid=${old_pids[0]}
    say "Starte $SERVICE_NAME kontrolliert neu (alte PID: $old_pid) ..."
    adb_shell "kill -TERM $old_pid" >/dev/null 2>&1 || { warn "TERM an PID $old_pid fehlgeschlagen; kein weiterer Eingriff."; return 1; }

    deadline=$((SECONDS + RESTART_TIMEOUT))
    while [ "$SECONDS" -lt "$deadline" ]; do
        sleep 1
        current=$(adb_shell "pidof $SERVICE_NAME" 2>/dev/null || true)
        current=${current//$'\r'/}
        for pid in $current; do
            if [[ "$pid" =~ ^[0-9]+$ ]] && [ "$pid" != "$old_pid" ]; then new_pid=$pid; break 2; fi
        done
    done
    if [ -n "$new_pid" ]; then
        say "$SERVICE_NAME wurde erfolgreich neu gestartet. Alte PID: $old_pid | Neue PID: $new_pid"
        return 0
    fi
    warn "$SERVICE_NAME-Neustart konnte innerhalb von ${RESTART_TIMEOUT}s nicht bestätigt werden. Kein weiterer Kill/Restart."
    return 1
}

status_heartbeat() {
    local stamp day logfile port lines
    trap 'exit 0' INT TERM
    while :; do
        sleep "$HEARTBEAT_INTERVAL" || exit 0
        stamp=$(date '+%Y-%m-%d %H:%M:%S'); day=${stamp%% *}; logfile="$LOG_DIR/phnix_$day.log"
        port=""; lines=0
        [ ! -s "$READY_FILE" ] || { IFS= read -r port < "$READY_FILE" || port=""; }
        if [ -f "$logfile" ]; then
            lines=$(wc -l < "$logfile" 2>/dev/null || printf '?\n'); lines=${lines//[[:space:]]/}; [ -n "$lines" ] || lines="?"
        fi
        if [ -n "$port" ]; then
            printf '[%s] Logger aktiv | Port: %s | Log: %s | Zeilen: %s\n' "$stamp" "$port" "${logfile##*/}" "$lines"
        else
            printf '[%s] Logger aktiv | Debugport getrennt - warte auf USB-Reconnect | Log: %s | Zeilen: %s\n' "$stamp" "${logfile##*/}" "$lines"
        fi
    done
}

parent_cleanup() {
    [ "$PARENT_CLEANED" -eq 0 ] || return 0
    PARENT_CLEANED=1
    trap - EXIT INT TERM
    if [ -n "$HEARTBEAT_PID" ] && kill -0 "$HEARTBEAT_PID" 2>/dev/null; then
        kill -TERM "$HEARTBEAT_PID" 2>/dev/null || true; wait "$HEARTBEAT_PID" 2>/dev/null || true
    fi
    if [ -n "$LOGGER_PID" ] && kill -0 "$LOGGER_PID" 2>/dev/null; then
        kill -TERM "$LOGGER_PID" 2>/dev/null || true; wait "$LOGGER_PID" 2>/dev/null || true
    fi
    rm -f -- "$READY_FILE"
}

handle_stop() {
    say ""
    say "Beende Logger. Am LTE-Modem wird nichts verändert."
    parent_cleanup
    exit 0
}

main() {
    local arg normalized adb_ok=0
    for arg in "$@"; do
        normalized=${arg,,}
        case "$normalized" in
            --help|-h) usage; return 0 ;;
            --no-restart|--norestart) NO_RESTART=1 ;;
            *) error "Unbekannte Option: $arg"; usage >&2; return 2 ;;
        esac
    done

    check_dependencies || return 3
    prepare_log_dir || return 4

    if select_adb_device; then
        adb_ok=1
        [ "$NO_RESTART" -eq 0 ] || say "--no-restart aktiv: ADB-Verbindung wurde geprüft; Dienst-Neustart wird übersprungen."
    else
        if [ "$NO_RESTART" -eq 0 ]; then
            say "Tipp: Mit './$PROGRAM_NAME --no-restart' kann trotz fehlgeschlagener ADB-Prüfung passiv geloggt werden."
            return 5
        fi
        warn "--no-restart aktiv: ADB-Prüfung fehlgeschlagen; passives serielles Logging läuft trotzdem weiter."
    fi

    rm -f -- "$READY_FILE"
    logger_supervisor &
    LOGGER_PID=$!
    say "Suche PHNIX-Debuginterface VID=$USB_VENDOR_ID PID=$USB_PRODUCT_ID IF=$USB_INTERFACE_NUM ..."
    wait_for_logger_ready || return 6
    say "Serielles Logging läuft. Tagesdatei: phnix_$(date +%F).log"

    if [ "$NO_RESTART" -eq 0 ] && [ "$adb_ok" -eq 1 ]; then
        wait_for_logger_ready || return 6
        restart_phnix_service_once || true
    fi

    say "Dauerlogging aktiv. Lebenszeichen alle 5 Minuten. Beenden mit Ctrl+C."
    status_heartbeat & HEARTBEAT_PID=$!
    wait "$LOGGER_PID"
}

trap handle_stop INT TERM
trap parent_cleanup EXIT
main "$@"
