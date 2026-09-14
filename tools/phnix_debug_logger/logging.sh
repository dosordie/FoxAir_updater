#!/usr/bin/env bash
# Passive PHNIX phnixIot4G debug logger for Raspberry Pi OS / Debian.
#
# PHNIX facts used here:
# - phnixIot4G writes its debug output to modem-side /dev/ttyGS0 at 115200 8N1.
# - The Raspberry Pi sees the debug endpoint as USB VID 1e0e / PID 9001 / IF 04.
# - On the Linux USB-serial side the baud rate is not forced: the SimTech USB
#   serial driver may reject a baud-rate change although the endpoint works.
# - USB re-enumeration is detected by the USB device generation (devnum), even
#   when Linux assigns the same /dev/ttyUSBx name after the reconnect.
# - A service restart is blocked while PHNIX OTA safety markers are present or
#   cannot be checked reliably. The original PHNIX OTA_INFO persistence is also
#   inspected independently of the serial debug stream.
# - OTA download/update markers are recognized passively from the debug stream.
# - In normal mode a silence watchdog may restart phnixIot4G once after 30
#   minutes without debug data. --no-restart disables all service restarts.
#
# The script never modifies the phnixIot4G binary or the modem filesystem.

set -u

PROGRAM_NAME=${0##*/}
SCRIPT_PATH=$(readlink -f "$0" 2>/dev/null || printf '%s\n' "$0")
USB_VENDOR_ID="1e0e"
USB_PRODUCT_ID="9001"
USB_INTERFACE_NUM="04"
SERVICE_NAME="phnixIot4G"
SCAN_INTERVAL=3
RESTART_TIMEOUT=25
HEARTBEAT_INTERVAL=300
SERIAL_READ_TIMEOUT=5
SILENCE_TIMEOUT=1800

DEFAULT_LOG_DIR="${HOME:-.}/FoxAir_Logs"
LOG_DIR="${LOG_DIR:-$DEFAULT_LOG_DIR}"
NO_RESTART=0
RUN_MODE="foreground"
DAEMON_MODE=0
ADB_SELECTED_SERIAL=""
LOGGER_PID=""
HEARTBEAT_PID=""
READY_FILE=""
BACKGROUND_READY_FILE=""
PID_FILE=""
STATUS_FILE=""
OTA_STATE_FILE=""
OTA_URL_LOG=""
PARENT_CLEANED=0

# These variables live in the serial logger worker. They are intentionally
# process-local and only serve to suppress duplicate PHNIX debug messages.
OTA_PHASE=""
OTA_LAST_URL=""
OTA_LAST_PROGRESS=""
OTA_SOFTWARE_CODE=""
OTA_VERSION=""
OTA_SSID=""
OTA_MD5=""
OTA_FILE_SIZE=""
OTA_URL_DETECTED=0

OTA_MARKERS=(
    "/tmp/phnix_ota_hook/run.active"
    "/tmp/phnix_ota_hook/transfer-started"
    "/tmp/phnix_ota_hook/original-service-owns"
)

color_enabled() {
    local fd="$1"
    [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != "dumb" ] && [ -t "$fd" ]
}

say() { printf '%s\n' "$*"; }

success() {
    if color_enabled 1; then
        printf '\033[32m%s\033[0m\n' "$*"
    else
        printf '%s\n' "$*"
    fi
}

warn() {
    if color_enabled 2; then
        printf '\033[33mWARNUNG: %s\033[0m\n' "$*" >&2
    else
        printf 'WARNUNG: %s\n' "$*" >&2
    fi
}

error() {
    if color_enabled 2; then
        printf '\033[31mFEHLER: %s\033[0m\n' "$*" >&2
    else
        printf 'FEHLER: %s\n' "$*" >&2
    fi
}

usage() {
    cat <<EOF_HELP
PHNIX Debug-Dauerlogger

Verwendung:
  ./$PROGRAM_NAME
  ./$PROGRAM_NAME --no-restart
  ./$PROGRAM_NAME --background [--no-restart]
  ./$PROGRAM_NAME --follow
  ./$PROGRAM_NAME --status
  ./$PROGRAM_NAME --stop
  ./$PROGRAM_NAME --help

Optionen:
  --no-restart   ADB prüfen, phnixIot4G aber nicht neu starten;
                 weder beim Start noch durch den 30-Minuten-Stumm-Watchdog.
                 USB-Wiederverbindung bleibt aktiv.
  --background   Logger im Hintergrund starten und Live-Status anzeigen.
  --follow       Live-Status eines laufenden Hintergrund-Loggers anzeigen.
                 Ctrl+C bzw. Schließen des Terminals beendet nur die Anzeige.
  --status       Einmaligen Status inkl. letztem OTA-Status anzeigen.
  --stop         Nur den Logger beenden; phnixIot4G bleibt unberührt.
  --help         Diese Hilfe anzeigen.

Zusätzliche Dateien:
  phnix_YYYY-MM-DD.log   vollständiger Roh-Debuglog mit Zeitstempeln
  phnix_ota_urls.log     erkannte Firmware-Download-URLs + Metadaten
  phnix_ota_state        letzter erkannter OTA-Zustand
  logger_status.log      Status-/Ereignisprotokoll ohne Farbcodes

Umgebungsvariablen:
  LOG_DIR        Zielverzeichnis der Logs (Standard: ~/FoxAir_Logs)
  ADB_SERIAL     ADB-Seriennummer erzwingen, falls mehrere Geräte verbunden sind.
  NO_COLOR       Farbausgabe im Terminal deaktivieren.

Der Debugport wird über VID $USB_VENDOR_ID / PID $USB_PRODUCT_ID /
USB-Interface $USB_INTERFACE_NUM ermittelt. Es gibt keine feste /dev/ttyUSBx-Nummer.
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

    for pair in "adb:adb" "udevadm:udev" "stty:coreutils" "stat:coreutils" "od:coreutils"; do
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

resolve_log_dir() {
    umask 077
    mkdir -p -- "$LOG_DIR" || { error "Logverzeichnis konnte nicht angelegt werden: $LOG_DIR"; return 1; }
    chmod 700 -- "$LOG_DIR" 2>/dev/null || true
    LOG_DIR=$(cd -- "$LOG_DIR" 2>/dev/null && pwd -P) || return 1
    PID_FILE="$LOG_DIR/phnix_logger.pid"
    STATUS_FILE="$LOG_DIR/logger_status.log"
    BACKGROUND_READY_FILE="$LOG_DIR/.phnix_debug_logger.ready"
    OTA_STATE_FILE="$LOG_DIR/phnix_ota_state"
    OTA_URL_LOG="$LOG_DIR/phnix_ota_urls.log"
}

prepare_log_dir() {
    resolve_log_dir || return 1

    if ! : >> "$OTA_URL_LOG"; then
        error "OTA-URL-Log kann nicht angelegt/beschrieben werden: $OTA_URL_LOG"
        return 1
    fi
    chmod 600 -- "$OTA_URL_LOG" 2>/dev/null || true

    say "Logverzeichnis: $LOG_DIR"
    say "OTA-URL-Log: $OTA_URL_LOG"
    warn "PHNIX-Debuglogs können IMEI/ICCID, ProductKey, DeviceSecret und andere Kennungen enthalten."
    warn "Firmware-Download-URLs können sensible bzw. temporär gültige Parameter enthalten."
    warn "Rohlogs und URL-Log vor einer Veröffentlichung immer prüfen."
}

read_background_pid() {
    BG_PID=""
    BG_SCRIPT=""
    [ -r "$PID_FILE" ] || return 1
    {
        IFS= read -r BG_PID || BG_PID=""
        IFS= read -r BG_SCRIPT || BG_SCRIPT=""
    } < "$PID_FILE"
    [[ "$BG_PID" =~ ^[0-9]+$ ]] || return 1
    return 0
}

pid_matches_background_daemon() {
    local pid="$1" expected_script="$2" cmdline=""
    [ -r "/proc/$pid/cmdline" ] || return 1
    cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
    [ -n "$cmdline" ] || return 1
    case "$cmdline" in
        *"$expected_script"*"--daemon"*) return 0 ;;
    esac
    return 1
}

background_state() {
    local BG_PID="" BG_SCRIPT=""
    if ! read_background_pid; then
        rm -f -- "$PID_FILE" 2>/dev/null || true
        return 1
    fi
    if ! kill -0 "$BG_PID" 2>/dev/null; then
        rm -f -- "$PID_FILE" "$BACKGROUND_READY_FILE" 2>/dev/null || true
        return 1
    fi
    if [ -z "$BG_SCRIPT" ] || ! pid_matches_background_daemon "$BG_PID" "$BG_SCRIPT"; then
        return 2
    fi
    return 0
}

write_daemon_pid_file() {
    local tmp="$PID_FILE.tmp.$$"
    printf '%s\n%s\n' "$$" "$SCRIPT_PATH" > "$tmp" || return 1
    mv -f -- "$tmp" "$PID_FILE" || return 1
}

remove_own_daemon_pid_file() {
    local pid="" script=""
    [ "$DAEMON_MODE" -eq 1 ] || return 0
    if [ -r "$PID_FILE" ]; then
        {
            IFS= read -r pid || pid=""
            IFS= read -r script || script=""
        } < "$PID_FILE"
        if [ "$pid" = "$$" ] && [ "$script" = "$SCRIPT_PATH" ]; then
            rm -f -- "$PID_FILE"
        fi
    fi
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
            error "Mehrere ADB-Geräte gefunden; es wird keines automatisch gewählt."
            print_adb_rows "${rows[@]}"
            say "Bei Bedarf ADB_SERIAL=<Seriennummer> vor dem Start setzen."
            return 1
        }
        serial=${serials[0]}; state=${states[0]}
    fi

    case "$state" in
        device) ADB_SELECTED_SERIAL="$serial"; success "ADB verbunden: $serial"; return 0 ;;
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

read_tty_usb_generation() {
    local dev="$1" tty_name=${1##*/} path vendor="" product="" devnum=""
    path=$(readlink -f "/sys/class/tty/$tty_name/device" 2>/dev/null || true)
    while [ -n "$path" ] && [ "$path" != "/" ]; do
        if [ -r "$path/idVendor" ] && [ -r "$path/idProduct" ]; then
            IFS= read -r vendor < "$path/idVendor" || vendor=""
            IFS= read -r product < "$path/idProduct" || product=""
            if [ "${vendor,,}" = "$USB_VENDOR_ID" ] && [ "${product,,}" = "$USB_PRODUCT_ID" ]; then
                [ -r "$path/devnum" ] && IFS= read -r devnum < "$path/devnum"
                printf '%s|%s\n' "$path" "$devnum"
                return 0
            fi
        fi
        path=${path%/*}; [ -n "$path" ] || path="/"
    done
    return 1
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
    warn "Kein eindeutiger PHNIX-Debugport gefunden."
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

json_string_value() {
    local text="$1" key="$2" re
    re="\"${key}\"[[:space:]]*:[[:space:]]*\"([^\"]*)\""
    if [[ "$text" =~ $re ]]; then
        printf '%s\n' "${BASH_REMATCH[1]}"
    fi
}

json_number_value() {
    local text="$1" key="$2" re
    re="\"${key}\"[[:space:]]*:[[:space:]]*([0-9]+)"
    if [[ "$text" =~ $re ]]; then
        printf '%s\n' "${BASH_REMATCH[1]}"
    fi
}

extract_download_url_candidate() {
    local text="$1" lower re
    lower=${text,,}
    re="([Hh][Tt][Tt][Pp][Ss]?|[Ff][Tt][Pp])://[^\"[:space:]]+"
    if [[ "$text" =~ $re ]]; then
        if [[ "$text" == *CMD_OTA* ]] || [[ "$text" == *otaDeviceInfo* ]] || \
           { [[ "$lower" == *firmware* || "$lower" == *upgrade* ]] && [[ "$lower" == *url* || "$lower" == *download* ]]; }; then
            printf '%s\n' "${BASH_REMATCH[0]}"
        fi
    fi
}

ota_write_state() {
    local stamp="$1" status="$2" progress="${3:-}" tmp
    tmp="$OTA_STATE_FILE.tmp.$$"
    {
        printf 'timestamp=%s\n' "$stamp"
        printf 'status=%s\n' "$status"
        printf 'progress=%s\n' "$progress"
        printf 'version=%s\n' "$OTA_VERSION"
        printf 'software_code=%s\n' "$OTA_SOFTWARE_CODE"
        printf 'ssid=%s\n' "$OTA_SSID"
        printf 'url_detected=%s\n' "$OTA_URL_DETECTED"
        printf 'url=%s\n' "$OTA_LAST_URL"
        printf 'md5=%s\n' "$OTA_MD5"
        printf 'file_size=%s\n' "$OTA_FILE_SIZE"
    } > "$tmp" || return 1
    mv -f -- "$tmp" "$OTA_STATE_FILE" || return 1
}

ota_emit() {
    local stamp="$1" status="$2" progress="${3:-}" display
    display="$status"
    if [ "$OTA_PHASE" = "$status" ] && { [ -z "$progress" ] || [ "$OTA_LAST_PROGRESS" = "$progress" ]; }; then
        return 0
    fi
    OTA_PHASE="$status"
    [ -z "$progress" ] || OTA_LAST_PROGRESS="$progress"
    ota_write_state "$stamp" "$status" "$progress" || true
    [ -z "$progress" ] || display="$status - $progress %"
    printf '[%s] OTA | %s\n' "$stamp" "$display"
}

ota_log_url() {
    local stamp="$1" url="$2"
    [ -n "$url" ] || return 0
    [ "$url" != "$OTA_LAST_URL" ] || return 0
    OTA_LAST_URL="$url"
    OTA_URL_DETECTED=1
    printf '[%s] URL=%s | SoftwareCode=%s | Version=%s | SSID=%s | MD5=%s | Size=%s\n' \
        "$stamp" "$url" "${OTA_SOFTWARE_CODE:-?}" "${OTA_VERSION:-?}" "${OTA_SSID:-?}" \
        "${OTA_MD5:-?}" "${OTA_FILE_SIZE:-?}" >> "$OTA_URL_LOG" || warn "OTA-URL-Log kann nicht geschrieben werden: $OTA_URL_LOG"
    ota_emit "$stamp" "Download-URL erkannt"
}

ota_process_line() {
    local raw="$1" stamp="$2" value="" url="" progress="" cmd="" ota_code="" assign_url_re=""

    case "$raw" in
        *otaFileDownloadAddr*|*CMD_OTA*|*otaDeviceInfo*|*http://*|*https://*|*ftp://*|*softwareCodeCloud=*|*deviceSoftwareVer=*|*download*%*|*succeed\ downloading\ package*|*固件MD5校验正确*|*传输主板升级文件偏移:0*|*oat\ step:6*|*升级包传输完成*|*主板升级成功\<5\>*|*主板升级结束*) ;;
        *) return 0 ;;
    esac

    cmd=$(json_string_value "$raw" "cmd" || true)
    ota_code=$(json_string_value "$raw" "code" || true)

    if [ "$cmd" = "CMD_OTA" ] && [ "$ota_code" = "0033" ]; then
        OTA_LAST_URL=""
        OTA_LAST_PROGRESS=""
        OTA_PHASE=""
        OTA_URL_DETECTED=0
        OTA_SOFTWARE_CODE=""
        OTA_VERSION=""
        OTA_SSID=""
        OTA_MD5=""
        OTA_FILE_SIZE=""
    fi

    value=$(json_string_value "$raw" "softwareCode" || true); [ -z "$value" ] || OTA_SOFTWARE_CODE="$value"
    value=$(json_string_value "$raw" "softwareVer" || true); [ -z "$value" ] || OTA_VERSION="$value"
    value=$(json_string_value "$raw" "ssid" || true); [ -z "$value" ] || OTA_SSID="$value"
    value=$(json_string_value "$raw" "fileMD5" || true); [ -z "$value" ] || OTA_MD5="$value"
    value=$(json_number_value "$raw" "fileSize" || true); [ -z "$value" ] || OTA_FILE_SIZE="$value"

    case "$raw" in
        *softwareCodeCloud=*) value=${raw#*softwareCodeCloud=}; value=${value%%[^[:alnum:]._-]*}; [ -z "$value" ] || OTA_SOFTWARE_CODE="$value" ;;
    esac
    case "$raw" in
        *deviceSoftwareVer=*) value=${raw#*deviceSoftwareVer=}; value=${value%%[^[:alnum:]._-]*}; [ -z "$value" ] || OTA_VERSION="$value" ;;
    esac
    case "$raw" in
        *otaDeviceInfo.ssid=*) value=${raw#*otaDeviceInfo.ssid=}; value=${value%%[^[:alnum:]._-]*}; [ -z "$value" ] || OTA_SSID="$value" ;;
    esac
    case "$raw" in
        *otaDeviceInfo.fileMD5=*) value=${raw#*otaDeviceInfo.fileMD5=}; value=${value%%[^[:alnum:]]*}; [ -z "$value" ] || OTA_MD5="$value" ;;
    esac
    case "$raw" in
        *otaDeviceInfo.fileSize=*) value=${raw#*otaDeviceInfo.fileSize=}; value=${value%%[^0-9]*}; [ -z "$value" ] || OTA_FILE_SIZE="$value" ;;
    esac

    url=$(json_string_value "$raw" "otaFileDownloadAddr" || true)
    assign_url_re="otaFileDownloadAddr[[:space:]]*=[[:space:]]*((([Hh][Tt][Tt][Pp][Ss]?)|([Ff][Tt][Pp]))://[^\"[:space:]]+)"
    if [ -z "$url" ] && [[ "$raw" =~ $assign_url_re ]]; then
        url=${BASH_REMATCH[1]}
    fi
    if [ -z "$url" ]; then
        url=$(extract_download_url_candidate "$raw" || true)
    fi
    [ -z "$url" ] || ota_log_url "$stamp" "$url"

    if [ "$cmd" = "CMD_OTA" ] && [ "$ota_code" = "0053" ]; then
        progress=$(json_string_value "$raw" "progress" || true)
        if [ "$progress" = "100" ]; then
            ota_emit "$stamp" "Firmware Update erfolgreich"
        fi
        return 0
    fi

    if [[ "$raw" =~ download[[:space:]]+([0-9]{1,3})% ]]; then
        progress=${BASH_REMATCH[1]}
        [ "$progress" = "$OTA_LAST_PROGRESS" ] && return 0
        if [ "$progress" = "0" ] && [ -z "$OTA_LAST_PROGRESS" ]; then
            ota_emit "$stamp" "Download gestartet" "$progress"
        else
            ota_emit "$stamp" "Download läuft" "$progress"
        fi
        return 0
    fi

    case "$raw" in
        *succeed\ downloading\ package*) ota_emit "$stamp" "Download abgeschlossen"; return 0 ;;
        *固件MD5校验正确*) ota_emit "$stamp" "MD5-Prüfung erfolgreich"; return 0 ;;
        *传输主板升级文件偏移:0*|*oat\ step:6*) ota_emit "$stamp" "Firmware Update läuft"; return 0 ;;
        *升级包传输完成*) ota_emit "$stamp" "Firmwareübertragung abgeschlossen - Mainboard verarbeitet Update"; return 0 ;;
        *主板升级成功\<5\>*) ota_emit "$stamp" "Firmware Update erfolgreich"; return 0 ;;
        *主板升级结束*) ota_emit "$stamp" "Firmware Update fertig"; return 0 ;;
    esac
}

ota_state_get() {
    local key="$1" line
    [ -r "$OTA_STATE_FILE" ] || return 1
    while IFS= read -r line; do
        case "$line" in
            "$key"=*) printf '%s\n' "${line#*=}"; return 0 ;;
        esac
    done < "$OTA_STATE_FILE"
    return 1
}

ota_state_blocks_restart() {
    local status=""
    [ -r "$OTA_STATE_FILE" ] || return 1
    status=$(ota_state_get status 2>/dev/null || true)
    case "$status" in
        "")
            warn "OTA-Zustandsdatei ist unklar; Neustart wird blockiert."
            return 0
            ;;
        "Firmware Update fertig")
            return 1
            ;;
        *)
            warn "OTA noch nicht abgeschlossen: '$status'; Neustart wird blockiert."
            return 0
            ;;
    esac
}

check_original_ota_persistence_safety() {
    local meta="/data/phnixIot_device_OTA_INFO"
    local statistic="/data/phnixIot_device_statisic"
    local cache="/cache/phnixIot_device_OTA"
    local output="" size="" values="" offset="" length=""
    local stat_size="" ssid="" cache_state=""
    local tmp_meta="" tmp_stat="" pulled_size=""

    output=$(adb_shell "if [ -e '$meta' ]; then wc -c < '$meta'; else echo MISSING; fi" 2>&1) || {
        warn "PHNIX OTA-Status konnte nicht gelesen werden; Neustart wird blockiert."
        return 1
    }
    output=${output//$'\r'/}
    size=${output##*$'\n'}
    size=${size//[[:space:]]/}

    if [ "$size" = "220" ]; then
        tmp_meta="$LOG_DIR/.phnix_ota_info.$$.$RANDOM"
        rm -f -- "$tmp_meta"

        if ! adb_run pull "$meta" "$tmp_meta" >/dev/null 2>&1; then
            rm -f -- "$tmp_meta"
            warn "OTA_INFO konnte nicht gelesen werden; Neustart wird blockiert."
            return 1
        fi

        pulled_size=$(stat -c %s -- "$tmp_meta" 2>/dev/null || printf '0\n')
        if [ "$pulled_size" != "220" ]; then
            rm -f -- "$tmp_meta"
            warn "OTA_INFO hat sich während der Prüfung geändert; Neustart wird blockiert."
            return 1
        fi

        values=$(od -An -N8 -j212 -tu4 "$tmp_meta" 2>/dev/null | tr -s '[:space:]' ' ')
        rm -f -- "$tmp_meta"
        read -r offset length <<< "$values"

        if ! [[ "$offset" =~ ^[0-9]+$ && "$length" =~ ^[0-9]+$ ]]; then
            warn "OTA_INFO konnte nicht ausgewertet werden; Neustart wird blockiert."
            return 1
        fi
        if [ "$length" -gt 0 ]; then
            warn "OTA aktiv oder fortsetzbar (Länge $length Byte, Offset $offset); Neustart wird blockiert."
            return 1
        fi
        if [ "$offset" -ne 0 ]; then
            warn "OTA_INFO ist unplausibel (Offset $offset bei Länge 0); Neustart wird blockiert."
            return 1
        fi
        return 0
    fi

    case "$size" in
        0|MISSING) ;;
        *)
            warn "OTA_INFO hat unerwartete Größe '${size:-unbekannt}'; Neustart wird blockiert."
            return 1
            ;;
    esac

    output=$(adb_shell "if [ -e '$cache' ]; then echo CACHE_PRESENT; else echo CACHE_ABSENT; fi; if [ -e '$statistic' ]; then wc -c < '$statistic'; else echo STAT_MISSING; fi" 2>&1) || {
        warn "Zusätzlicher PHNIX OTA-Status konnte nicht gelesen werden; Neustart wird blockiert."
        return 1
    }
    output=${output//$'\r'/}
    cache_state=${output%%$'\n'*}
    stat_size=${output##*$'\n'}
    stat_size=${stat_size//[[:space:]]/}

    if [ "$cache_state" = "CACHE_PRESENT" ]; then
        warn "Firmware-Cache vorhanden; mögliches OTA läuft. Neustart wird blockiert."
        return 1
    fi
    if [ "$cache_state" != "CACHE_ABSENT" ]; then
        warn "Firmware-Cache-Status ist unklar; Neustart wird blockiert."
        return 1
    fi

    case "$stat_size" in
        128)
            tmp_stat="$LOG_DIR/.phnix_ota_stat.$$.$RANDOM"
            rm -f -- "$tmp_stat"

            if ! adb_run pull "$statistic" "$tmp_stat" >/dev/null 2>&1; then
                rm -f -- "$tmp_stat"
                warn "PHNIX Statistikdatei konnte nicht gelesen werden; Neustart wird blockiert."
                return 1
            fi

            pulled_size=$(stat -c %s -- "$tmp_stat" 2>/dev/null || printf '0\n')
            if [ "$pulled_size" != "128" ]; then
                rm -f -- "$tmp_stat"
                warn "Statistikdatei hat sich während der Prüfung geändert; Neustart wird blockiert."
                return 1
            fi

            ssid=$(od -An -N2 -j124 -tu2 "$tmp_stat" 2>/dev/null | tr -d '[:space:]')
            rm -f -- "$tmp_stat"

            if ! [[ "$ssid" =~ ^[0-9]+$ ]]; then
                warn "Board-OTA-SSID konnte nicht ausgewertet werden; Neustart wird blockiert."
                return 1
            fi
            if [ "$ssid" -ne 0 ]; then
                warn "Board-OTA-SSID=$ssid gesetzt; möglicher OTA-Start. Neustart wird blockiert."
                return 1
            fi
            ;;
        0|STAT_MISSING)
            ;;
        *)
            warn "PHNIX Statistikdatei hat unerwartete Größe '${stat_size:-unbekannt}'; Neustart wird blockiert."
            return 1
            ;;
    esac

    warn "OTA_INFO fehlt/ist leer, aber keine OTA-Aktivität erkennbar; Neustart wird erlaubt."
    return 0
}

latest_raw_log_epoch() {
    local f epoch latest=0
    for f in "$LOG_DIR"/phnix_????-??-??.log; do
        [ -s "$f" ] || continue
        epoch=$(stat -c %Y -- "$f" 2>/dev/null || printf '0\n')
        [[ "$epoch" =~ ^[0-9]+$ ]] || epoch=0
        [ "$epoch" -gt "$latest" ] && latest=$epoch
    done
    printf '%s\n' "$latest"
}

write_log_line() {
    local raw="$1" stamp day logfile
    raw=${raw%$'\r'}
    stamp=$(date '+%Y-%m-%d %H:%M:%S')
    day=${stamp%% *}
    logfile="$LOG_DIR/phnix_$day.log"
    printf '[%s] %s\n' "$stamp" "$raw" >> "$logfile" || { error "Logdatei kann nicht geschrieben werden: $logfile"; return 1; }
    ota_process_line "$raw" "$stamp"
}

logger_supervisor() {
    local port="" saved_stty="" line="" attempts=0 fd_open=0 cleaned=1
    local opened_generation="" current_generation="" read_rc=0 pending=""

    worker_cleanup() {
        [ "$cleaned" -eq 0 ] || return 0
        cleaned=1
        [ "$fd_open" -eq 0 ] || { exec 3<&- || true; fd_open=0; }
        if [ -n "$port" ] && [ -n "$saved_stty" ] && [ -c "$port" ]; then
            current_generation=$(read_tty_usb_generation "$port" 2>/dev/null || true)
            if [ -z "$opened_generation" ] || [ "$current_generation" = "$opened_generation" ]; then
                stty -F "$port" "$saved_stty" >/dev/null 2>&1 || true
            fi
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
                say "Warte auf Debugport (${SCAN_INTERVAL}s) ..."
            fi
            sleep "$SCAN_INTERVAL"
            continue
        fi

        cleaned=0
        saved_stty=$(stty -F "$port" -g 2>/dev/null || true)
        if [ -z "$saved_stty" ]; then
            error "Serielle Einstellungen von $port können nicht gelesen werden."
            cleaned=1; sleep "$SCAN_INTERVAL"; continue
        fi

        if ! stty -F "$port" cs8 -parenb -cstopb -ixon -ixoff -ixany -crtscts \
            -icanon -echo -echoe -echok -echonl -icrnl -inlcr -igncr -istrip min 1 time 0 2>/dev/null; then
            error "$port konnte nicht für USB-Serial konfiguriert werden."
            worker_cleanup; port=""; saved_stty=""; sleep "$SCAN_INTERVAL"; continue
        fi

        if ! exec 3<"$port"; then
            error "$port konnte nicht geöffnet werden."
            worker_cleanup; port=""; saved_stty=""; sleep "$SCAN_INTERVAL"; continue
        fi
        fd_open=1
        opened_generation=$(read_tty_usb_generation "$port" 2>/dev/null || true)
        pending=""
        success "Debugport verbunden: $port"
        printf '%s\n' "$port" > "$READY_FILE"
        : >> "$LOG_DIR/phnix_$(date +%F).log" || warn "Tages-Logdatei konnte nicht angelegt werden."

        while :; do
            line=""
            IFS= read -r -t "$SERIAL_READ_TIMEOUT" line <&3
            read_rc=$?
            if [ "$read_rc" -eq 0 ]; then
                line="$pending$line"
                pending=""
                write_log_line "$line" || return 1
                continue
            fi
            [ -z "$line" ] || pending="$pending$line"

            if [ -n "$opened_generation" ]; then
                current_generation=$(read_tty_usb_generation "$port" 2>/dev/null || true)
                if [ "$current_generation" != "$opened_generation" ]; then
                    warn "USB-Verbindung wurde neu aufgebaut. Debugport wird neu geöffnet."
                    break
                fi
            else
                if ! discover_debug_port >/dev/null 2>&1; then
                    warn "Debugport getrennt. Suche Verbindung neu."
                    break
                fi
            fi

            if [ "$read_rc" -lt 128 ]; then
                warn "Lesen von $port beendet (Status $read_rc). Debugport wird neu geöffnet."
                break
            fi
        done

        rm -f -- "$READY_FILE"
        worker_cleanup
        port=""; saved_stty=""; opened_generation=""; current_generation=""; pending=""
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

    if ota_state_blocks_restart; then
        return 1
    fi

    for marker in "${OTA_MARKERS[@]}"; do
        output=$(adb_shell "if [ -e '$marker' ]; then echo PRESENT; else echo ABSENT; fi" 2>&1) || {
            warn "OTA-Schutzmarker konnte nicht geprüft werden: $marker"; return 1;
        }
        state=${output%$'\r'}; state=${state##*$'\n'}
        case "$state" in
            ABSENT) ;;
            PRESENT) warn "OTA-Schutzmarker vorhanden: $marker"; return 1 ;;
            *) warn "Unerwartete Antwort beim Prüfen von $marker: ${output:-<leer>}"; return 1 ;;
        esac
    done

    check_original_ota_persistence_safety || return 1
    return 0
}

restart_phnix_service_once() {
    local output old_pid current pid deadline new_pid=""
    local -a old_pids=()

    if ! check_ota_restart_safety; then
        warn "$SERVICE_NAME wird nicht neu gestartet; Logging läuft weiter."
        return 1
    fi
    output=$(adb_shell "pidof $SERVICE_NAME" 2>&1) || { warn "$SERVICE_NAME-PID konnte nicht ermittelt werden; kein Neustart."; return 1; }
    read -r -a old_pids <<< "${output//$'\r'/}"
    if [ "${#old_pids[@]}" -ne 1 ] || ! [[ "${old_pids[0]}" =~ ^[0-9]+$ ]]; then
        warn "Keine eindeutige $SERVICE_NAME-PID gefunden (${output:-<leer>}); kein Neustart."
        return 1
    fi
    old_pid=${old_pids[0]}
    say "Starte $SERVICE_NAME neu (PID $old_pid) ..."
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
        success "$SERVICE_NAME neu gestartet: $old_pid -> $new_pid"
        return 0
    fi
    warn "$SERVICE_NAME-Neustart konnte innerhalb von ${RESTART_TIMEOUT}s nicht bestätigt werden."
    return 1
}

status_heartbeat() {
    local stamp day logfile port lines interval="$HEARTBEAT_INTERVAL" sleep_pid="" ota_status=""
    local now_epoch watchdog_reference_epoch observed_rx_epoch=0 silent_for=0 silent_minutes=0
    local silence_restart_attempted=0 silence_notice_emitted=0
    [ "$DAEMON_MODE" -eq 0 ] || interval=60

    watchdog_reference_epoch=$(date +%s)
    observed_rx_epoch=$(latest_raw_log_epoch)
    if [ "$observed_rx_epoch" -gt "$watchdog_reference_epoch" ]; then
        watchdog_reference_epoch=$observed_rx_epoch
    fi

    heartbeat_stop() {
        if [ -n "$sleep_pid" ] && kill -0 "$sleep_pid" 2>/dev/null; then
            kill -TERM "$sleep_pid" 2>/dev/null || true
            wait "$sleep_pid" 2>/dev/null || true
        fi
        exit 0
    }

    trap heartbeat_stop INT TERM
    while :; do
        sleep "$interval" &
        sleep_pid=$!
        wait "$sleep_pid" || exit 0
        sleep_pid=""

        stamp=$(date '+%Y-%m-%d %H:%M:%S'); day=${stamp%% *}; logfile="$LOG_DIR/phnix_$day.log"
        port=""; lines=0; ota_status=""
        [ ! -s "$READY_FILE" ] || { IFS= read -r port < "$READY_FILE" || port=""; }
        if [ -f "$logfile" ]; then
            lines=$(wc -l < "$logfile" 2>/dev/null || printf '?\n'); lines=${lines//[[:space:]]/}; [ -n "$lines" ] || lines="?"
        fi

        observed_rx_epoch=$(latest_raw_log_epoch)
        if [ "$observed_rx_epoch" -gt "$watchdog_reference_epoch" ]; then
            watchdog_reference_epoch=$observed_rx_epoch
            silence_restart_attempted=0
            silence_notice_emitted=0
        fi
        now_epoch=$(date +%s)
        silent_for=$((now_epoch - watchdog_reference_epoch))
        [ "$silent_for" -ge 0 ] || silent_for=0
        silent_minutes=$((silent_for / 60))

        ota_status=$(ota_state_get status 2>/dev/null || true)
        if [ -n "$port" ]; then
            printf '[%s] OK | %s | %s Zeilen | letzte Daten vor %s min' "$stamp" "$port" "$lines" "$silent_minutes"
        else
            printf '[%s] USB getrennt | %s Zeilen | letzte Daten vor %s min' "$stamp" "$lines" "$silent_minutes"
        fi
        [ -z "$ota_status" ] || printf ' | OTA: %s' "$ota_status"
        printf '\n'

        if [ "$silent_for" -ge "$SILENCE_TIMEOUT" ]; then
            if [ "$NO_RESTART" -eq 1 ]; then
                if [ "$silence_notice_emitted" -eq 0 ]; then
                    warn "Seit ${silent_minutes} min keine Debugdaten. --no-restart aktiv; kein Dienstneustart."
                    silence_notice_emitted=1
                fi
            elif [ -z "$port" ]; then
                if [ "$silence_notice_emitted" -eq 0 ]; then
                    warn "Seit ${silent_minutes} min keine Debugdaten, aber USB ist getrennt. Warte auf Wiederverbindung."
                    silence_notice_emitted=1
                fi
            elif [ "$silence_restart_attempted" -eq 0 ]; then
                warn "Seit ${silent_minutes} min keine Debugdaten. Prüfe OTA-Schutz vor automatischem Neustart."
                silence_restart_attempted=1
                silence_notice_emitted=1
                restart_phnix_service_once || true
            fi
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
    [ -z "$READY_FILE" ] || rm -f -- "$READY_FILE"
    remove_own_daemon_pid_file
}

handle_stop() {
    say ""
    if [ "$DAEMON_MODE" -eq 1 ]; then
        say "Hintergrund-Logger wird beendet. Am LTE-Modem wird nichts verändert."
    else
        say "Beende Logger. Am LTE-Modem wird nichts verändert."
    fi
    parent_cleanup
    exit 0
}

run_logger_core() {
    local adb_ok=0

    check_dependencies || return 3
    prepare_log_dir || return 4

    if [ "$DAEMON_MODE" -eq 1 ]; then
        READY_FILE="$BACKGROUND_READY_FILE"
        rm -f -- "$READY_FILE"
        write_daemon_pid_file || { error "PID-Datei konnte nicht geschrieben werden: $PID_FILE"; return 7; }
        say "Logger PID: $$"
    else
        READY_FILE="${TMPDIR:-/tmp}/phnix_debug_logger.$$.${RANDOM}.ready"
    fi

    trap handle_stop INT TERM
    trap parent_cleanup EXIT

    if select_adb_device; then
        adb_ok=1
        [ "$NO_RESTART" -eq 0 ] || say "--no-restart aktiv: Dienst-Neustarts sind aus."
    else
        if [ "$NO_RESTART" -eq 0 ]; then
            say "Tipp: Mit './$PROGRAM_NAME --no-restart' kann trotzdem passiv geloggt werden."
            return 5
        fi
        warn "ADB-Prüfung fehlgeschlagen; passives serielles Logging läuft weiter."
    fi

    rm -f -- "$READY_FILE"
    logger_supervisor &
    LOGGER_PID=$!
    say "Suche PHNIX-Debugport ..."
    wait_for_logger_ready || return 6
    success "Logging aktiv: phnix_$(date +%F).log"
    success "USB-Wiederverbindung aktiv."

    if [ "$NO_RESTART" -eq 0 ] && [ "$adb_ok" -eq 1 ]; then
        wait_for_logger_ready || return 6
        restart_phnix_service_once || true
    fi

    if [ "$NO_RESTART" -eq 0 ] && [ "$adb_ok" -eq 1 ]; then
        say "Stumm-Watchdog aktiv: Neustart nach 30 min ohne Daten (max. 1x pro Stummphase)."
    else
        say "Stumm-Watchdog: Dienstneustart aus; USB-Wiederverbindung bleibt aktiv."
    fi

    if [ "$DAEMON_MODE" -eq 1 ]; then
        say "Hintergrundlogging aktiv. Status alle 60 s."
    else
        say "Logging aktiv. Status alle 5 min. Ende mit Ctrl+C."
    fi
    status_heartbeat & HEARTBEAT_PID=$!
    wait "$LOGGER_PID"
}

show_ota_status() {
    local stamp status progress version code ssid url_detected md5 size
    if [ ! -r "$OTA_STATE_FILE" ]; then
        say "OTA: noch kein Firmware-Update erkannt."
        if [ -e "$OTA_URL_LOG" ] && [ -w "$OTA_URL_LOG" ]; then
            say "OTA-URL-Log: bereit, noch leer"
        else
            say "OTA-URL-Log: nicht schreibbereit"
        fi
        return 0
    fi

    stamp=$(ota_state_get timestamp 2>/dev/null || true)
    status=$(ota_state_get status 2>/dev/null || true)
    progress=$(ota_state_get progress 2>/dev/null || true)
    version=$(ota_state_get version 2>/dev/null || true)
    code=$(ota_state_get software_code 2>/dev/null || true)
    ssid=$(ota_state_get ssid 2>/dev/null || true)
    url_detected=$(ota_state_get url_detected 2>/dev/null || true)
    md5=$(ota_state_get md5 2>/dev/null || true)
    size=$(ota_state_get file_size 2>/dev/null || true)

    say "OTA: ${status:-unbekannt}"
    [ -z "$stamp" ] || say "Zeit: $stamp"
    [ -z "$progress" ] || say "Fortschritt: $progress %"
    [ -z "$version" ] || say "Version: $version"
    [ -z "$code" ] || say "SoftwareCode: $code"
    [ -z "$ssid" ] || say "SSID: $ssid"
    if [ "$url_detected" = "1" ]; then
        success "Download-URL erkannt: ja"
        say "OTA-URL-Log: ${OTA_URL_LOG##*/}"
    fi
    [ -z "$md5" ] || say "MD5: $md5"
    [ -z "$size" ] || say "Dateigröße: $size Byte"
}

show_background_status() {
    local rc pid="" port="" day logfile lines=0 last="" last_rx_epoch=0 now_epoch=0 rx_age=0 rx_stamp=""
    resolve_log_dir || return 4

    background_state
    rc=$?
    if [ "$rc" -eq 2 ]; then
        error "PID-Datei zeigt auf einen fremden Prozess. Keine Aktion."
        return 8
    fi
    if [ "$rc" -ne 0 ]; then
        say "Hintergrund-Logger läuft nicht."
        [ ! -f "$STATUS_FILE" ] || { last=$(tail -n 1 "$STATUS_FILE" 2>/dev/null || true); [ -z "$last" ] || say "Letzter Status: $last"; }
        show_ota_status
        return 1
    fi

    read_background_pid || return 1
    pid=$BG_PID
    [ ! -s "$BACKGROUND_READY_FILE" ] || { IFS= read -r port < "$BACKGROUND_READY_FILE" || port=""; }
    day=$(date +%F); logfile="$LOG_DIR/phnix_$day.log"
    if [ -f "$logfile" ]; then
        lines=$(wc -l < "$logfile" 2>/dev/null || printf '?\n'); lines=${lines//[[:space:]]/}; [ -n "$lines" ] || lines="?"
    fi

    success "Logger läuft (PID $pid)."
    if [ -n "$port" ]; then success "Debugport verbunden: $port"; else warn "Debugport getrennt / noch nicht bereit"; fi
    say "Heute: $lines Zeilen"

    last_rx_epoch=$(latest_raw_log_epoch)
    if [ "$last_rx_epoch" -gt 0 ]; then
        now_epoch=$(date +%s)
        rx_age=$((now_epoch - last_rx_epoch)); [ "$rx_age" -ge 0 ] || rx_age=0
        rx_stamp=$(date -d "@$last_rx_epoch" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || printf '%s' "$last_rx_epoch")
        say "Letzte Daten: $rx_stamp (vor $((rx_age / 60)) min)"
    else
        say "Letzte Daten: noch keine Debugzeile"
    fi

    show_ota_status
    [ ! -f "$STATUS_FILE" ] || { last=$(tail -n 1 "$STATUS_FILE" 2>/dev/null || true); [ -z "$last" ] || say "Letzter Status: $last"; }
    return 0
}

colorize_status_stream() {
    local line red green yellow reset

    if ! color_enabled 1; then
        cat
        return
    fi

    red=$'\033[31m'
    green=$'\033[32m'
    yellow=$'\033[33m'
    reset=$'\033[0m'

    while IFS= read -r line; do
        case "$line" in
            FEHLER:*)
                printf '%s%s%s\n' "$red" "$line" "$reset"
                ;;
            WARNUNG:*)
                printf '%s%s%s\n' "$yellow" "$line" "$reset"
                ;;
            *"ADB verbunden:"*|*"Debugport verbunden:"*|*"neu gestartet:"*|*"Download-URL erkannt"*|*"Firmware Update erfolgreich"*|*"Firmware Update fertig"*|*"Logging aktiv:"*|*"USB-Wiederverbindung aktiv"*|*"Logger gestartet:"*)
                printf '%s%s%s\n' "$green" "$line" "$reset"
                ;;
            *)
                printf '%s\n' "$line"
                ;;
        esac
    done
}

follow_background_status() {
    local rc viewer_interrupted=0
    resolve_log_dir || return 4

    background_state
    rc=$?
    if [ "$rc" -eq 2 ]; then
        error "PID-Datei zeigt auf einen fremden Prozess. Live-Anzeige wird nicht gestartet."
        return 8
    fi
    if [ "$rc" -ne 0 ]; then
        error "Kein laufender Hintergrund-Logger gefunden."
        return 1
    fi

    touch "$STATUS_FILE" || { error "Statusdatei kann nicht geöffnet werden: $STATUS_FILE"; return 4; }
    say ""
    say "Live-Status (Ctrl+C beendet nur die Anzeige)."
    say "Logger läuft im Hintergrund weiter. Ereignisse sofort, Status alle 60 s."
    say ""

    trap 'viewer_interrupted=1' INT TERM
    tail -n 20 -F "$STATUS_FILE" | colorize_status_stream
    rc=$?
    trap - INT TERM

    if [ "$viewer_interrupted" -eq 1 ] || [ "$rc" -eq 130 ] || [ "$rc" -eq 143 ]; then
        say ""
        say "Live-Anzeige beendet. Hintergrund-Logger läuft weiter."
        return 0
    fi
    return "$rc"
}

stop_background_logger() {
    local rc pid="" i
    resolve_log_dir || return 4

    background_state
    rc=$?
    if [ "$rc" -eq 2 ]; then
        error "PID-Datei zeigt auf einen fremden Prozess. Es wird nichts beendet."
        return 8
    fi
    if [ "$rc" -ne 0 ]; then
        say "Hintergrund-Logger läuft nicht."
        return 0
    fi

    read_background_pid || return 1
    pid=$BG_PID
    say "Beende Logger PID $pid ..."
    kill -TERM "$pid" 2>/dev/null || { error "TERM an Logger PID $pid fehlgeschlagen."; return 1; }

    for i in $(seq 1 50); do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f -- "$PID_FILE" "$BACKGROUND_READY_FILE" 2>/dev/null || true
            success "Logger beendet. phnixIot4G wurde nicht verändert."
            return 0
        fi
        sleep 0.2
    done

    warn "Logger PID $pid läuft nach 10 Sekunden noch. Kein SIGKILL wird verwendet."
    return 1
}

start_background_logger() {
    local rc launcher_pid="" i
    local -a daemon_args=("--daemon")

    resolve_log_dir || return 4
    background_state
    rc=$?
    if [ "$rc" -eq 0 ]; then
        read_background_pid || true
        success "Logger läuft bereits (PID ${BG_PID:-?})."
        follow_background_status
        return $?
    fi
    if [ "$rc" -eq 2 ]; then
        error "PID-Datei zeigt auf einen fremden Prozess. Neuer Logger wird nicht gestartet."
        return 8
    fi

    command -v nohup >/dev/null 2>&1 || { error "'nohup' fehlt (Paket coreutils)."; return 3; }
    command -v tail >/dev/null 2>&1 || { error "'tail' fehlt (Paket coreutils)."; return 3; }

    [ "$NO_RESTART" -eq 0 ] || daemon_args+=("--no-restart")
    rm -f -- "$PID_FILE" "$BACKGROUND_READY_FILE"
    : > "$STATUS_FILE" || { error "Statusdatei kann nicht geschrieben werden: $STATUS_FILE"; return 4; }

    if command -v setsid >/dev/null 2>&1; then
        nohup setsid "$SCRIPT_PATH" "${daemon_args[@]}" >> "$STATUS_FILE" 2>&1 </dev/null &
    else
        nohup "$SCRIPT_PATH" "${daemon_args[@]}" >> "$STATUS_FILE" 2>&1 </dev/null &
    fi
    launcher_pid=$!

    for i in $(seq 1 50); do
        if background_state; then
            read_background_pid || true
            success "Logger gestartet: PID ${BG_PID:-$launcher_pid}"
            say "Statusdatei: $STATUS_FILE"
            say "Terminal darf geschlossen werden; der Logger läuft weiter."
            follow_background_status
            return $?
        fi
        sleep 0.2
    done

    error "Hintergrund-Logger hat innerhalb von 10 Sekunden keine gültige PID-Datei angelegt."
    [ ! -f "$STATUS_FILE" ] || tail -n 30 "$STATUS_FILE" >&2
    return 1
}

parse_args() {
    local arg normalized action_seen=0
    for arg in "$@"; do
        normalized=${arg,,}
        case "$normalized" in
            --help|-h)
                RUN_MODE="help"
                ;;
            --no-restart|--norestart)
                NO_RESTART=1
                ;;
            --background)
                [ "$action_seen" -eq 0 ] || { error "Nur eine Aktionsoption gleichzeitig verwenden."; return 2; }
                RUN_MODE="background"; action_seen=1
                ;;
            --follow)
                [ "$action_seen" -eq 0 ] || { error "Nur eine Aktionsoption gleichzeitig verwenden."; return 2; }
                RUN_MODE="follow"; action_seen=1
                ;;
            --status)
                [ "$action_seen" -eq 0 ] || { error "Nur eine Aktionsoption gleichzeitig verwenden."; return 2; }
                RUN_MODE="status"; action_seen=1
                ;;
            --stop)
                [ "$action_seen" -eq 0 ] || { error "Nur eine Aktionsoption gleichzeitig verwenden."; return 2; }
                RUN_MODE="stop"; action_seen=1
                ;;
            --daemon)
                [ "$action_seen" -eq 0 ] || { error "Nur eine Aktionsoption gleichzeitig verwenden."; return 2; }
                RUN_MODE="daemon"; DAEMON_MODE=1; action_seen=1
                ;;
            *)
                error "Unbekannte Option: $arg"
                return 2
                ;;
        esac
    done

    case "$RUN_MODE" in
        follow|status|stop)
            if [ "$NO_RESTART" -eq 1 ]; then
                warn "--no-restart hat bei --$RUN_MODE keine Wirkung und wird ignoriert."
            fi
            ;;
    esac
    return 0
}

main() {
    parse_args "$@" || { usage >&2; return 2; }

    case "$RUN_MODE" in
        help) usage ;;
        foreground) run_logger_core ;;
        daemon) run_logger_core ;;
        background) start_background_logger ;;
        follow) follow_background_status ;;
        status) show_background_status ;;
        stop) stop_background_logger ;;
        *) error "Interner Fehler: unbekannter Modus '$RUN_MODE'"; return 2 ;;
    esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
