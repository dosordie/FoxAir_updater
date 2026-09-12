#!/usr/bin/env bash
# Passive PHNIX phnixIot4G debug logger for Raspberry Pi OS / Debian.
#
# Repository facts reused here:
# - phnixIot4G opens /dev/ttyGS0 as its debug output at 115200 8N1.
# - The host-side USB composite interface is VID 1e0e / PID 9001 / interface 04.
# - A service restart must be blocked while any PHNIX OTA safety marker is present
#   or cannot be checked reliably.
#
# The logger never modifies the phnixIot4G binary or the LTE modem filesystem.
# ADB is only used for the optional one-time guarded service restart at startup.

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

usage() {
    cat <<EOF_HELP
PHNIX Debug-Dauerlogger

Verwendung:
  ./$PROGRAM_NAME
  ./$PROGRAM_NAME --no-restart
  ./$PROGRAM_NAME --help

Optionen:
  --no-restart   phnixIot4G nicht neu starten; nur passiv mitloggen.
  --help         Diese Hilfe anzeigen.

Umgebungsvariablen:
  LOG_DIR        Zielverzeichnis der Logs (Standard: ~/FoxAir_Logs)
  ADB_SERIAL     ADB-Seriennummer erzwingen, falls mehrere ADB-Geräte verbunden sind.

Das Script sucht den seriellen Debugport ausschließlich über
VID $USB_VENDOR_ID / PID $USB_PRODUCT_ID / USB-Interface $USB_INTERFACE_NUM und
verwendet keine fest eingetragene /dev/ttyUSBx-Portnummer.
EOF_HELP
}

say() {
    printf '%s\n' "$*"
}

warn() {
    printf 'WARNUNG: %s\n' "$*" >&2
}

error() {
    printf 'FEHLER: %s\n' "$*" >&2
}

manual_install_help() {
    local packages="$1"
    local apt_cmd="${2:-apt-get}"

    say ""
    say "Manuelle Installation auf Raspberry Pi OS / Debian:"
    if [ "${EUID:-$(id -u)}" -eq 0 ]; then
        printf '  %s update\n' "$apt_cmd"
        printf '  %s install %s\n' "$apt_cmd" "$packages"
    elif command -v sudo >/dev/null 2>&1; then
        printf '  sudo %s update\n' "$apt_cmd"
        printf '  sudo %s install %s\n' "$apt_cmd" "$packages"
    else
        say "  Als root anmelden (z. B. mit 'su -') und ausführen:"
        printf '  %s update\n' "$apt_cmd"
        printf '  %s install %s\n' "$apt_cmd" "$packages"
    fi
}

check_dependencies() {
    local -a missing_cmds=()
    local -a packages=()
    local cmd pkg candidate seen package_string apt_cmd answer

    for candidate in "adb:adb" "udevadm:udev" "stty:coreutils"; do
        cmd=${candidate%%:*}
        pkg=${candidate#*:}
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing_cmds+=("$cmd")
            seen=0
            if [ "${#packages[@]}" -gt 0 ]; then
                for package_string in "${packages[@]}"; do
                    if [ "$package_string" = "$pkg" ]; then
                        seen=1
                        break
                    fi
                done
            fi
            [ "$seen" -eq 1 ] || packages+=("$pkg")
        fi
    done

    if [ "${#missing_cmds[@]}" -eq 0 ]; then
        return 0
    fi

    error "Folgende benötigte Programme fehlen: ${missing_cmds[*]}"
    say "Benötigte Debian-Pakete: ${packages[*]}"

    apt_cmd=""
    if [ -e /etc/debian_version ]; then
        if command -v apt-get >/dev/null 2>&1; then
            apt_cmd="apt-get"
        elif command -v apt >/dev/null 2>&1; then
            apt_cmd="apt"
        fi
    fi

    package_string="${packages[*]}"
    if [ -z "$apt_cmd" ]; then
        error "Keine unterstützte Debian/Raspberry-Pi-OS-Paketverwaltung (apt/apt-get) erkannt."
        manual_install_help "$package_string" "apt-get"
        return 1
    fi

    if [ "${EUID:-$(id -u)}" -ne 0 ] && ! command -v sudo >/dev/null 2>&1; then
        error "Für die automatische Installation wären root-Rechte nötig, aber 'sudo' fehlt."
        manual_install_help "$package_string" "$apt_cmd"
        return 1
    fi

    printf 'Fehlende Pakete automatisch installieren? [j/N] '
    answer=""
    if ! { IFS= read -r answer </dev/tty; } 2>/dev/null; then
        answer=""
        warn "Keine interaktive Konsole verfügbar; automatische Installation wird nicht gestartet."
    fi

    case "$answer" in
        j|J|ja|JA|Ja|y|Y|yes|YES|Yes)
            ;;
        *)
            say "Keine automatische Installation durchgeführt."
            manual_install_help "$package_string" "$apt_cmd"
            return 1
            ;;
    esac

    say "Installiere ausschließlich die fehlenden Pakete: $package_string"
    if [ "${EUID:-$(id -u)}" -eq 0 ]; then
        "$apt_cmd" update || return 1
        "$apt_cmd" install -y "${packages[@]}" || return 1
    else
        sudo "$apt_cmd" update || return 1
        sudo "$apt_cmd" install -y "${packages[@]}" || return 1
    fi

    for cmd in "${missing_cmds[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            error "'$cmd' ist nach der Installation weiterhin nicht verfügbar."
            return 1
        fi
    done
}

prepare_log_dir() {
    local existed=0
    [ -d "$LOG_DIR" ] && existed=1

    umask 077
    if ! mkdir -p -- "$LOG_DIR"; then
        error "Logverzeichnis konnte nicht angelegt werden: $LOG_DIR"
        return 1
    fi
    if [ "$existed" -eq 0 ]; then
        chmod 700 -- "$LOG_DIR" 2>/dev/null || true
    fi

    LOG_DIR=$(cd -- "$LOG_DIR" 2>/dev/null && pwd -P) || {
        error "Logverzeichnis konnte nicht aufgelöst werden: $LOG_DIR"
        return 1
    }

    say "Logverzeichnis: $LOG_DIR"
    warn "PHNIX-Debuglogs können IMEI/ICCID, ProductKey, DeviceSecret und andere Kennungen enthalten."
    warn "Rohlogs vor einer Veröffentlichung immer manuell prüfen."
}

adb_base() {
    if [ -n "$ADB_SELECTED_SERIAL" ]; then
        printf '%s\n' "adb" "-s" "$ADB_SELECTED_SERIAL"
    else
        printf '%s\n' "adb"
    fi
}

adb_run() {
    local -a base=()
    mapfile -t base < <(adb_base)
    "${base[@]}" "$@"
}

adb_shell() {
    adb_run shell "$@"
}

print_adb_rows() {
    local row
    say "Gefundene ADB-Geräte:"
    if [ "$#" -eq 0 ]; then
        say "  (keine)"
        return
    fi
    for row in "$@"; do
        printf '  %s\n' "$row"
    done
}

select_adb_device() {
    local output line serial state rest
    local -a rows=()
    local -a serials=()
    local -a states=()
    local i found=-1

    if ! adb start-server >/dev/null 2>&1; then
        error "ADB-Server konnte nicht gestartet werden."
        return 1
    fi

    if ! output=$(adb devices 2>&1); then
        error "'adb devices' ist fehlgeschlagen:"
        printf '%s\n' "$output" >&2
        return 1
    fi

    while IFS= read -r line; do
        line=${line%$'\r'}
        [ -n "$line" ] || continue
        case "$line" in
            "List of devices attached"*|"* daemon"*) continue ;;
        esac
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
            if [ "${serials[$i]}" = "$ADB_SERIAL" ]; then
                found=$i
                break
            fi
        done
        if [ "$found" -lt 0 ]; then
            error "ADB_SERIAL='$ADB_SERIAL' wurde nicht gefunden."
            print_adb_rows "${rows[@]}"
            return 1
        fi
        serial=${serials[$found]}
        state=${states[$found]}
    else
        if [ "${#serials[@]}" -eq 0 ]; then
            error "Kein ADB-Gerät gefunden. USB-Verbindung zum PHNIX-Modem prüfen."
            return 1
        fi
        if [ "${#serials[@]}" -gt 1 ]; then
            error "Mehrere ADB-Geräte gefunden; aus Sicherheitsgründen wird keines automatisch gewählt."
            print_adb_rows "${rows[@]}"
            say "Bei Bedarf ADB_SERIAL=<Seriennummer> vor dem Start setzen."
            return 1
        fi
        serial=${serials[0]}
        state=${states[0]}
    fi

    case "$state" in
        device)
            ADB_SELECTED_SERIAL="$serial"
            say "ADB-Gerät: $ADB_SELECTED_SERIAL"
            return 0
            ;;
        unauthorized)
            error "ADB-Gerät '$serial' ist unauthorized. ADB-Autorisierung am Gerät prüfen."
            return 1
            ;;
        offline)
            error "ADB-Gerät '$serial' ist offline. USB-/ADB-Verbindung neu herstellen."
            return 1
            ;;
        *)
            error "ADB-Gerät '$serial' ist nicht bereit (Status: $state)."
            return 1
            ;;
    esac
}

read_sysfs_usb_info() {
    local tty_name="$1"
    local path vendor="" product="" iface=""

    path=$(readlink -f "/sys/class/tty/$tty_name/device" 2>/dev/null || true)
    while [ -n "$path" ] && [ "$path" != "/" ]; do
        if [ -z "$iface" ] && [ -r "$path/bInterfaceNumber" ]; then
            IFS= read -r iface < "$path/bInterfaceNumber" || iface=""
        fi
        if [ -z "$vendor" ] && [ -r "$path/idVendor" ]; then
            IFS= read -r vendor < "$path/idVendor" || vendor=""
        fi
        if [ -z "$product" ] && [ -r "$path/idProduct" ]; then
            IFS= read -r product < "$path/idProduct" || product=""
        fi
        if [ -n "$vendor" ] && [ -n "$product" ] && [ -n "$iface" ]; then
            break
        fi
        path=${path%/*}
        [ -n "$path" ] || path="/"
    done

    vendor=${vendor,,}
    product=${product,,}
    iface=${iface,,}
    printf '%s|%s|%s\n' "$vendor" "$product" "$iface"
}

read_tty_usb_info() {
    local dev="$1"
    local tty_name=${dev##*/}
    local props key value
    local vendor="" product="" iface=""
    local sysinfo sys_vendor sys_product sys_iface

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
        IFS='|' read -r sys_vendor sys_product sys_iface <<< "$sysinfo"
        [ -n "$vendor" ] || vendor=$sys_vendor
        [ -n "$product" ] || product=$sys_product
        [ -n "$iface" ] || iface=$sys_iface
    fi

    printf '%s|%s|%s\n' "$vendor" "$product" "$iface"
}

discover_debug_port() {
    local sys_tty tty_name dev info vendor product iface
    local -a matches=()

    for sys_tty in /sys/class/tty/*; do
        [ -e "$sys_tty" ] || continue
        tty_name=${sys_tty##*/}
        dev="/dev/$tty_name"
        [ -c "$dev" ] || continue

        info=$(read_tty_usb_info "$dev")
        IFS='|' read -r vendor product iface <<< "$info"
        if [ "$vendor" = "$USB_VENDOR_ID" ] \
            && [ "$product" = "$USB_PRODUCT_ID" ] \
            && [ "$iface" = "$USB_INTERFACE_NUM" ]; then
            matches+=("$dev")
        fi
    done

    if [ "${#matches[@]}" -eq 1 ]; then
        printf '%s\n' "${matches[0]}"
        return 0
    fi
    if [ "${#matches[@]}" -gt 1 ]; then
        return 2
    fi
    return 1
}

print_tty_diagnostics() {
    local sys_tty tty_name dev info vendor product iface
    local -a exact=()
    local -a same_usb=()
    local -a generic=()

    for sys_tty in /sys/class/tty/*; do
        [ -e "$sys_tty" ] || continue
        tty_name=${sys_tty##*/}
        dev="/dev/$tty_name"
        [ -c "$dev" ] || continue
        info=$(read_tty_usb_info "$dev")
        IFS='|' read -r vendor product iface <<< "$info"

        if [ "$vendor" = "$USB_VENDOR_ID" ] && [ "$product" = "$USB_PRODUCT_ID" ]; then
            same_usb+=("$dev  VID=$vendor PID=$product IF=${iface:-?}")
            [ "$iface" = "$USB_INTERFACE_NUM" ] && exact+=("$dev  VID=$vendor PID=$product IF=$iface")
        elif [[ "$tty_name" == ttyUSB* || "$tty_name" == ttyACM* ]]; then
            generic+=("$dev  VID=${vendor:-?} PID=${product:-?} IF=${iface:-?}")
        fi
    done

    if [ "${#exact[@]}" -gt 1 ]; then
        warn "Mehrere exakte PHNIX-Debuginterfaces gefunden; keine Schnittstelle wird geöffnet:"
        printf '  %s\n' "${exact[@]}" >&2
        return
    fi
    if [ "${#same_usb[@]}" -gt 0 ]; then
        warn "PHNIX USB-Gerät gefunden, aber Debuginterface $USB_INTERFACE_NUM ist nicht eindeutig verfügbar:"
        printf '  %s\n' "${same_usb[@]}" >&2
        return
    fi
    if [ "${#generic[@]}" -gt 0 ]; then
        warn "Kein passendes PHNIX-Debuginterface gefunden. Sichtbare USB-TTY-Kandidaten:"
        printf '  %s\n' "${generic[@]}" >&2
        return
    fi
    warn "Kein passendes PHNIX-Debuginterface und keine ttyUSB/ttyACM-Kandidaten gefunden."
}

write_log_line() {
    local raw="$1"
    local stamp day logfile

    raw=${raw%$'\r'}
    stamp=$(date '+%Y-%m-%d %H:%M:%S')
    day=${stamp%% *}
    logfile="$LOG_DIR/phnix_$day.log"
    if ! printf '[%s] %s\n' "$stamp" "$raw" >> "$logfile"; then
        error "Logdatei kann nicht geschrieben werden: $logfile"
        return 1
    fi
}

logger_supervisor() {
    local port="" saved_stty="" line="" attempts=0
    local fd_open=0 worker_cleaned=0

    worker_cleanup() {
        [ "$worker_cleaned" -eq 0 ] || return 0
        worker_cleaned=1
        if [ "$fd_open" -eq 1 ]; then
            exec 3<&- || true
            fd_open=0
        fi
        if [ -n "$port" ] && [ -n "$saved_stty" ] && [ -c "$port" ]; then
            stty -F "$port" "$saved_stty" >/dev/null 2>&1 || true
        fi
    }

    worker_stop() {
        worker_cleanup
        exit 0
    }

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

        # From here on cleanup must restore this connection attempt even if a
        # signal arrives between termios configuration and opening the read FD.
        worker_cleaned=0
        saved_stty=$(stty -F "$port" -g 2>/dev/null || true)
        if [ -z "$saved_stty" ]; then
            error "Serielle Einstellungen von $port können nicht gelesen werden (Berechtigung?)."
            say "Hinweis: Auf Raspberry Pi OS gehört der Port häufig zur Gruppe 'dialout'."
            sleep "$SCAN_INTERVAL"
            continue
        fi

        if ! stty -F "$port" 115200 cs8 -parenb -cstopb -ixon -ixoff -ixany -crtscts \
            -icanon -echo -echoe -echok -echonl -icrnl -inlcr -igncr -istrip min 1 time 0 2>/dev/null; then
            error "$port konnte nicht auf 115200 8N1 ohne Flow-Control konfiguriert werden."
            stty -F "$port" "$saved_stty" >/dev/null 2>&1 || true
            sleep "$SCAN_INTERVAL"
            continue
        fi

        if ! exec 3<"$port"; then
            error "$port konnte nicht zum Lesen geöffnet werden."
            stty -F "$port" "$saved_stty" >/dev/null 2>&1 || true
            sleep "$SCAN_INTERVAL"
            continue
        fi
        fd_open=1

        say "PHNIX-Debugport verbunden: $port (115200 8N1)"
        printf '%s\n' "$port" > "$READY_FILE"

        while :; do
            line=""
            if IFS= read -r line <&3; then
                write_log_line "$line" || return 1
                continue
            fi
            if [ -n "$line" ]; then
                write_log_line "$line" || return 1
            fi
            break
        done

        warn "PHNIX-Debugport $port wurde getrennt. Suche nach erneutem USB-Connect ..."
        rm -f -- "$READY_FILE"
        worker_cleaned=0
        worker_cleanup
        port=""
        saved_stty=""
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
    local marker state output

    for marker in "${OTA_MARKERS[@]}"; do
        if ! output=$(adb_shell "if [ -e '$marker' ]; then echo PRESENT; else echo ABSENT; fi" 2>&1); then
            warn "OTA-Schutzmarker konnte nicht sicher geprüft werden: $marker"
            return 1
        fi
        state=${output%$'\r'}
        state=${state##*$'\n'}
        case "$state" in
            ABSENT)
                ;;
            PRESENT)
                warn "OTA-Schutzmarker ist vorhanden: $marker"
                return 1
                ;;
            *)
                warn "Unerwartete Antwort beim Prüfen von $marker: ${output:-<leer>}"
                return 1
                ;;
        esac
    done
    return 0
}

restart_phnix_service_once() {
    local output old_pid current pid deadline new_pid=""
    local -a old_pids=()

    if ! check_ota_restart_safety; then
        warn "$SERVICE_NAME wird NICHT neu gestartet. Möglicherweise ist ein Firmwareupdate aktiv oder noch nicht sicher abgeschlossen."
        warn "Das passive serielle Logging läuft weiter."
        return 1
    fi

    if ! output=$(adb_shell "pidof $SERVICE_NAME" 2>&1); then
        warn "$SERVICE_NAME-Prozess konnte per ADB nicht ermittelt werden; kein Neustart."
        warn "ADB-Ausgabe: ${output:-<leer>}"
        return 1
    fi

    read -r -a old_pids <<< "${output//$'\r'/}"
    if [ "${#old_pids[@]}" -ne 1 ] || ! [[ "${old_pids[0]}" =~ ^[0-9]+$ ]]; then
        warn "Keine eindeutige $SERVICE_NAME-PID gefunden (${output:-<leer>}); kein Neustart."
        return 1
    fi
    old_pid=${old_pids[0]}

    say "Starte $SERVICE_NAME kontrolliert neu (alte PID: $old_pid) ..."
    if ! output=$(adb_shell "kill -TERM $old_pid" 2>&1); then
        warn "TERM an $SERVICE_NAME PID $old_pid ist fehlgeschlagen; kein weiterer Eingriff."
        warn "ADB-Ausgabe: ${output:-<leer>}"
        return 1
    fi

    deadline=$((SECONDS + RESTART_TIMEOUT))
    while [ "$SECONDS" -lt "$deadline" ]; do
        sleep 1
        current=$(adb_shell "pidof $SERVICE_NAME" 2>/dev/null || true)
        current=${current//$'\r'/}
        for pid in $current; do
            if [[ "$pid" =~ ^[0-9]+$ ]] && [ "$pid" != "$old_pid" ]; then
                new_pid=$pid
                break 2
            fi
        done
    done

    if [ -n "$new_pid" ]; then
        say "$SERVICE_NAME wurde erfolgreich neu gestartet."
        say "Alte PID: $old_pid"
        say "Neue PID: $new_pid"
        return 0
    fi

    warn "$SERVICE_NAME-Neustart konnte innerhalb von ${RESTART_TIMEOUT}s nicht durch eine neue PID bestätigt werden."
    warn "Es wird kein weiterer Kill/Restart versucht; das passive Logging läuft weiter."
    return 1
}

status_heartbeat() {
    local stamp day logfile port lines

    trap 'exit 0' INT TERM

    while :; do
        sleep "$HEARTBEAT_INTERVAL" || exit 0

        stamp=$(date '+%Y-%m-%d %H:%M:%S')
        day=${stamp%% *}
        logfile="$LOG_DIR/phnix_$day.log"
        port=""
        lines=0

        if [ -s "$READY_FILE" ]; then
            IFS= read -r port < "$READY_FILE" || port=""
        fi
        if [ -f "$logfile" ]; then
            lines=$(wc -l < "$logfile" 2>/dev/null || printf '?\n')
            lines=${lines//[[:space:]]/}
            [ -n "$lines" ] || lines="?"
        fi

        if [ -n "$port" ]; then
            printf '[%s] Logger aktiv | Port: %s | Log: %s | Zeilen: %s\n' \
                "$stamp" "$port" "${logfile##*/}" "$lines"
        else
            printf '[%s] Logger aktiv | Debugport getrennt - warte auf USB-Reconnect | Log: %s | Zeilen: %s\n' \
                "$stamp" "${logfile##*/}" "$lines"
        fi
    done
}

parent_cleanup() {
    [ "$PARENT_CLEANED" -eq 0 ] || return 0
    PARENT_CLEANED=1
    trap - EXIT INT TERM

    if [ -n "$HEARTBEAT_PID" ] && kill -0 "$HEARTBEAT_PID" 2>/dev/null; then
        kill -TERM "$HEARTBEAT_PID" 2>/dev/null || true
        wait "$HEARTBEAT_PID" 2>/dev/null || true
    fi
    if [ -n "$LOGGER_PID" ] && kill -0 "$LOGGER_PID" 2>/dev/null; then
        kill -TERM "$LOGGER_PID" 2>/dev/null || true
        wait "$LOGGER_PID" 2>/dev/null || true
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
    local arg

    for arg in "$@"; do
        case "$arg" in
            --help|-h)
                usage
                return 0
                ;;
            --no-restart)
                NO_RESTART=1
                ;;
            *)
                error "Unbekannte Option: $arg"
                usage >&2
                return 2
                ;;
        esac
    done

    check_dependencies || return 3
    prepare_log_dir || return 4

    if [ "$NO_RESTART" -eq 0 ]; then
        if ! select_adb_device; then
            say "Tipp: Mit './$PROGRAM_NAME --no-restart' kann ausschließlich passiv geloggt werden."
            return 5
        fi
    else
        say "--no-restart aktiv: ADB-Geräteauswahl und Dienst-Neustart werden übersprungen."
    fi

    rm -f -- "$READY_FILE"
    logger_supervisor &
    LOGGER_PID=$!

    say "Suche PHNIX-Debuginterface VID=$USB_VENDOR_ID PID=$USB_PRODUCT_ID IF=$USB_INTERFACE_NUM ..."
    wait_for_logger_ready || return 6
    say "Serielles Logging läuft. Tagesdatei: phnix_$(date +%F).log"

    if [ "$NO_RESTART" -eq 0 ]; then
        # Confirm the logger is still connected immediately before the one-time
        # restart attempt. Reconnects are handled only inside logger_supervisor
        # and never trigger this code again.
        wait_for_logger_ready || return 6
        restart_phnix_service_once || true
    fi

    say "Dauerlogging aktiv. Lebenszeichen alle 5 Minuten. Beenden mit Ctrl+C."
    status_heartbeat &
    HEARTBEAT_PID=$!
    wait "$LOGGER_PID"
}

trap handle_stop INT TERM
trap parent_cleanup EXIT

main "$@"
