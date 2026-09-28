#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="https://github.com/dosordie/FoxAir_updater.git"
INSTALL_DIR="${FOX_AIR_INSTALL_DIR:-$HOME/FoxAir_updater}"
UDEV_RULE_FILE="/etc/udev/rules.d/51-foxair-android.rules"
UDEV_RULE='SUBSYSTEM=="usb", ATTR{idVendor}=="1e0e", ATTR{idProduct}=="9001", MODE="0666"'
REMOTE_ADB_SERVICE_FILE="/etc/systemd/system/foxair-adb-remote.service"
REMOTE_DEBUG_SERVICE_FILE="/etc/systemd/system/foxair-debug-stream.service"
REMOTE_ADB_PORT=5038
REMOTE_DEBUG_PORT=5039
REMOTE_ACCESS_MODE="${FOX_AIR_REMOTE_ACCESS:-ask}"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10
SPARSE_PATHS=(
    updater/common
    updater/dtu_ota
    updater/linux
    tools/phnix_ota
    docs/HowTo
)

ok()   { printf '[OK] %s\n' "$*"; }
info() { printf '[..] %s\n' "$*"; }
warn() { printf '[WARNUNG] %s\n' "$*" >&2; }
die()  { printf '[FEHLER] %s\n' "$*" >&2; exit 1; }

installer_usage() {
    cat <<'TXT'
FoxAir Linux Installer

Verwendung:
  bash install.sh
  bash install.sh --remote-access
  bash install.sh --no-remote-access

--remote-access     ADB TCP 5038 und PHNIX-Debug TCP 5039 installieren,
                    beim Boot aktivieren und sofort starten.
--no-remote-access  Dienste installieren, aber deaktiviert/gestoppt lassen.

Ohne Option wird bei einer interaktiven Erstinstallation gefragt. Ein bereits
aktivierter Remotezugriff bleibt bei späteren Updates aktiviert.
TXT
}

for arg in "$@"; do
    case "$arg" in
        --remote-access) REMOTE_ACCESS_MODE="enable" ;;
        --no-remote-access) REMOTE_ACCESS_MODE="disable" ;;
        -h|--help) installer_usage; exit 0 ;;
        *) die "Unbekannte Installer-Option: $arg" ;;
    esac
done

configure_sparse_checkout() {
    if ! git -C "$INSTALL_DIR" sparse-checkout init --cone; then
        die "git sparse-checkout konnte nicht initialisiert werden ($(git --version))."
    fi
    if ! git -C "$INSTALL_DIR" sparse-checkout set "${SPARSE_PATHS[@]}"; then
        die "Die Linux-Dateiauswahl per git sparse-checkout konnte nicht eingerichtet werden."
    fi
}

adb_has_device() {
    printf '%s\n' "$1" | awk 'NR>1 && $2 == "device" {found=1} END {exit !found}'
}

adb_has_offline() {
    printf '%s\n' "$1" | awk 'NR>1 && $2 == "offline" {found=1} END {exit !found}'
}

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    die "Bitte den Installer als normaler Benutzer starten. sudo wird bei Bedarf automatisch verwendet."
fi

# Beim Update kann diese Datei selbst durch git pull ersetzt werden. Falls der
# Installer aus dem Ziel-Repository gestartet wurde, zuerst aus /tmp neu starten.
if [[ "${FOX_AIR_INSTALLER_REEXEC:-0}" != "1" ]]; then
    script_path="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || true)"
    install_path="$(readlink -f "$INSTALL_DIR" 2>/dev/null || true)"
    if [[ -n "$script_path" && -n "$install_path" && "$script_path" == "$install_path"/* ]]; then
        tmp_installer="$(mktemp /tmp/foxair-install.XXXXXX.sh)"
        cp "$script_path" "$tmp_installer"
        chmod 700 "$tmp_installer"
        if FOX_AIR_INSTALLER_REEXEC=1 bash "$tmp_installer" "$@"; then
            rc=0
        else
            rc=$?
        fi
        rm -f "$tmp_installer"
        exit "$rc"
    fi
fi

command -v sudo >/dev/null 2>&1 || die "sudo wurde nicht gefunden. Der Installer benötigt sudo nur für Systempakete und die udev-Regel."

missing_packages=()
command -v python3 >/dev/null 2>&1 || missing_packages+=(python3)
command -v adb >/dev/null 2>&1 || missing_packages+=(adb)
command -v lsusb >/dev/null 2>&1 || missing_packages+=(usbutils)
command -v git >/dev/null 2>&1 || missing_packages+=(git)
[[ -f /etc/ssl/certs/ca-certificates.crt ]] || missing_packages+=(ca-certificates)

if (( ${#missing_packages[@]} > 0 )); then
    if ! command -v apt-get >/dev/null 2>&1; then
        die "Fehlende Programme: ${missing_packages[*]}. Automatische Installation wird derzeit nur auf Debian/Ubuntu/Raspberry Pi OS mit apt unterstützt."
    fi
    info "Installiere fehlende Abhängigkeiten: ${missing_packages[*]}"
    sudo apt-get update
    sudo apt-get install -y "${missing_packages[@]}"
    ok "Systemabhängigkeiten installiert"
else
    ok "Systemabhängigkeiten vorhanden"
fi

python_version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
if ! python3 -c "import sys; raise SystemExit(0 if sys.version_info >= ($MIN_PYTHON_MAJOR, $MIN_PYTHON_MINOR) else 1)"; then
    die "Python $python_version gefunden. Benötigt wird Python >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}."
fi
ok "Python $python_version"
ok "Git verfügbar ($(git --version))"

if [[ -e "$INSTALL_DIR" && ! -d "$INSTALL_DIR" ]]; then
    die "$INSTALL_DIR existiert, ist aber kein Verzeichnis."
fi

if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Vorhandene Installation gefunden: $INSTALL_DIR"
    git -C "$INSTALL_DIR" config core.fileMode false

    origin_url="$(git -C "$INSTALL_DIR" remote get-url origin 2>/dev/null || true)"
    case "$origin_url" in
        https://github.com/dosordie/FoxAir_updater.git|https://github.com/dosordie/FoxAir_updater|git@github.com:dosordie/FoxAir_updater.git)
            ;;
        *)
            die "Das vorhandene Repository verwendet einen unerwarteten origin: ${origin_url:-<nicht gesetzt>}"
            ;;
    esac

    branch="$(git -C "$INSTALL_DIR" branch --show-current)"
    [[ "$branch" == "main" ]] || die "Das vorhandene Repository steht auf Branch '$branch'. Erwartet wird 'main'."

    if [[ -n "$(git -C "$INSTALL_DIR" status --porcelain --untracked-files=no)" ]]; then
        git -C "$INSTALL_DIR" status --short --untracked-files=no >&2
        die "Lokale Änderungen an Projektdateien gefunden. Automatisches Update wurde nicht durchgeführt."
    fi

    old_commit="$(git -C "$INSTALL_DIR" rev-parse --short HEAD)"
    info "Aktualisiere Repository von GitHub"
    git -C "$INSTALL_DIR" pull --ff-only origin main
    new_commit="$(git -C "$INSTALL_DIR" rev-parse --short HEAD)"
    if [[ "$old_commit" == "$new_commit" ]]; then
        ok "FoxAir Updater ist bereits aktuell ($new_commit)"
    else
        ok "FoxAir Updater aktualisiert: $old_commit -> $new_commit"
    fi

    # Falls ein älterer Installer gerade das Update auf eine neue Installer-
    # Version durchgeführt hat, die neue Version einmal übernehmen.
    current_script="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || true)"
    repo_installer="$INSTALL_DIR/updater/linux/install.sh"
    if [[ "${FOX_AIR_INSTALLER_POST_UPDATE:-0}" != "1" && -f "$repo_installer" && -n "$current_script" ]] \
       && ! cmp -s "$current_script" "$repo_installer"; then
        info "Neue Installer-Version erkannt; setze Installation mit aktuellem Installer fort"
        exec env FOX_AIR_INSTALLER_REEXEC=1 FOX_AIR_INSTALLER_POST_UPDATE=1 bash "$repo_installer" "$@"
    fi

    info "Reduziere Checkout auf die für Linux benötigten Dateien"
    configure_sparse_checkout
    ok "Sparse-Checkout eingerichtet"
elif [[ -d "$INSTALL_DIR" && -n "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    die "$INSTALL_DIR existiert bereits und ist kein FoxAir-Updater-Git-Repository."
else
    info "Lade FoxAir Updater nach $INSTALL_DIR"
    git clone --filter=blob:none --no-checkout --branch main --single-branch "$REPO_URL" "$INSTALL_DIR"
    git -C "$INSTALL_DIR" config core.fileMode false
    configure_sparse_checkout
    git -C "$INSTALL_DIR" checkout main
    ok "Repository als schlanker Linux-Checkout installiert"
fi

mkdir -p "$INSTALL_DIR/firmware" "$INSTALL_DIR/downloaded_firmware" "$INSTALL_DIR/logs"
ok "Lokaler Firmware-Ordner bereit: $INSTALL_DIR/firmware"
ok "Lokaler Download-/Backup-Ordner bereit: $INSTALL_DIR/downloaded_firmware"
ok "Lokaler Update-/Diagnose-Logordner bereit: $INSTALL_DIR/logs"

# Die internen Werkzeuge bleiben direkt ausführbar; der Anwender verwendet im
# Normalfall den Launcher im Projekt-Hauptverzeichnis.
chmod 755 \
    "$INSTALL_DIR/foxair-updater" \
    "$INSTALL_DIR/tools/phnix_ota/create_firmware_manifest.py" \
    "$INSTALL_DIR/updater/dtu_ota/payload/phnix_ota_runtime_hook" \
    "$INSTALL_DIR/updater/linux/autonomous_update.py" \
    "$INSTALL_DIR/updater/linux/remote_debug_stream.py" \
    "$INSTALL_DIR/updater/linux/remote_access.sh" \
    "$INSTALL_DIR/updater/linux/install.sh"
ok "Dateirechte gesetzt"

info "Richte USB-Zugriff für PHNIX LTE-Modem 1e0e:9001 ein"
current_rule=""
if sudo test -f "$UDEV_RULE_FILE"; then
    current_rule="$(sudo cat "$UDEV_RULE_FILE" 2>/dev/null || true)"
fi
if [[ "$current_rule" != "$UDEV_RULE" ]]; then
    printf '%s\n' "$UDEV_RULE" | sudo tee "$UDEV_RULE_FILE" >/dev/null
    sudo chmod 644 "$UDEV_RULE_FILE"
    ok "udev-Regel geschrieben: $UDEV_RULE_FILE"
else
    ok "udev-Regel bereits vorhanden"
fi

if command -v udevadm >/dev/null 2>&1; then
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    ok "udev-Regeln neu geladen"
else
    warn "udevadm wurde nicht gefunden; die USB-Regel wird spätestens nach erneutem Anstecken/Neustart wirksam."
fi

remote_was_enabled=0
if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-enabled --quiet foxair-adb-remote.service 2>/dev/null \
       || systemctl is-enabled --quiet foxair-debug-stream.service 2>/dev/null; then
        remote_was_enabled=1
    fi

    adb_path="$(command -v adb)"
    python_path="$(command -v python3)"
    install_user="$(id -un)"
    install_home="$HOME"

    info "Installiere integrierten Remotezugriff (ADB 5038 / PHNIX-Debug 5039)"
    sudo tee "$REMOTE_ADB_SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=FoxAir remote ADB server on TCP $REMOTE_ADB_PORT
After=network.target

[Service]
Type=simple
User=$install_user
Environment=HOME=$install_home
ExecStartPre=-/usr/bin/env ADB_SERVER_SOCKET=tcp:127.0.0.1:$REMOTE_ADB_PORT $adb_path kill-server
ExecStartPre=-$adb_path kill-server
ExecStart=$adb_path -a -P $REMOTE_ADB_PORT nodaemon server
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

    sudo tee "$REMOTE_DEBUG_SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=FoxAir read-only PHNIX debug stream on TCP $REMOTE_DEBUG_PORT
After=network.target foxair-adb-remote.service

[Service]
Type=simple
User=$install_user
SupplementaryGroups=dialout
ExecStart=$python_path $INSTALL_DIR/updater/linux/remote_debug_stream.py --bind 0.0.0.0 --port $REMOTE_DEBUG_PORT
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
    sudo chmod 644 "$REMOTE_ADB_SERVICE_FILE" "$REMOTE_DEBUG_SERVICE_FILE"
    sudo systemctl daemon-reload
    ok "Remote-Dienste installiert"

    if [[ "$REMOTE_ACCESS_MODE" == "ask" && "$remote_was_enabled" -eq 1 ]]; then
        REMOTE_ACCESS_MODE="enable"
    elif [[ "$REMOTE_ACCESS_MODE" == "ask" && -t 0 ]]; then
        printf 'Remotezugriff für Windows aktivieren (ADB :5038 + PHNIX-Debug :5039)? [j/N] '
        read -r remote_answer
        case "${remote_answer,,}" in
            j|ja|y|yes) REMOTE_ACCESS_MODE="enable" ;;
            *) REMOTE_ACCESS_MODE="disable" ;;
        esac
    elif [[ "$REMOTE_ACCESS_MODE" == "ask" ]]; then
        REMOTE_ACCESS_MODE="disable"
    fi

    if [[ "$REMOTE_ACCESS_MODE" == "enable" ]]; then
        "$INSTALL_DIR/updater/linux/remote_access.sh" enable
        export ADB_SERVER_SOCKET="tcp:127.0.0.1:$REMOTE_ADB_PORT"
        warn "Remote-ADB ist für ein vertrauenswürdiges LAN gedacht. TCP $REMOTE_ADB_PORT/$REMOTE_DEBUG_PORT nicht ins Internet weiterleiten."
    else
        "$INSTALL_DIR/updater/linux/remote_access.sh" disable >/dev/null 2>&1 || true
        ok "Remotezugriff installiert, aber nicht aktiviert"
        info "Später aktivieren mit: $INSTALL_DIR/foxair-updater remote enable"
    fi
else
    warn "systemd wurde nicht gefunden; Remote-ADB/Debug-Dienste wurden nicht installiert."
fi

info "Prüfe FoxAir-Updater-Dateien"
(
    cd "$INSTALL_DIR"
    python3 tools/phnix_ota/create_firmware_manifest.py --help >/dev/null
    python3 updater/dtu_ota/cli.py --help >/dev/null
    python3 updater/dtu_ota/original_state.py --help >/dev/null
    python3 updater/linux/autonomous_update.py --help >/dev/null
    python3 updater/linux/remote_debug_stream.py --help >/dev/null
    bash -n updater/linux/remote_access.sh
    ./foxair-updater --help >/dev/null
)
ok "Updater und Launcher erfolgreich geprüft"

if [[ -n "${ADB_SERVER_SOCKET:-}" ]]; then
    info "Verwende integrierten ADB-Server: $ADB_SERVER_SOCKET"
    ok "Remote-ADB-Server läuft"
else
    info "Starte lokalen ADB-Server"
    adb kill-server >/dev/null 2>&1 || true
    adb start-server >/dev/null
    ok "ADB-Server läuft"
fi

# Das PHNIX-LTE-Modem kann unmittelbar nach einem ADB-Neustart kurz als
# "offline" erscheinen, obwohl USB und Berechtigungen bereits korrekt sind.
# Deshalb zunächst kurz warten und bei genau diesem Zustand einmal reconnecten.
sleep 1
adb_output="$(adb devices -l 2>&1 || true)"
if ! adb_has_device "$adb_output" && adb_has_offline "$adb_output"; then
    info "ADB-Gerät ist noch offline; verbinde Transport erneut"
    adb reconnect >/dev/null 2>&1 || true
    sleep 2
    adb_output="$(adb devices -l 2>&1 || true)"
fi

# Nach einem Reconnect noch einige Sekunden auf den fertigen ADB-Handshake warten.
if ! adb_has_device "$adb_output"; then
    for _ in 1 2 3 4 5; do
        sleep 1
        adb_output="$(adb devices -l 2>&1 || true)"
        adb_has_device "$adb_output" && break
    done
fi

printf '\n%s\n' "$adb_output"
if adb_has_device "$adb_output"; then
    ok "ADB-Gerät erkannt"
elif adb_has_offline "$adb_output"; then
    warn "ADB-Gerät wurde erkannt, ist aber weiterhin 'offline'. Bitte 'adb reconnect' und danach 'adb devices -l' ausführen."
else
    warn "Kein ADB-Gerät im Status 'device' erkannt. Die Installation ist trotzdem abgeschlossen. Modem anschließen und 'adb devices -l' erneut ausführen."
fi

commit="$(git -C "$INSTALL_DIR" rev-parse --short HEAD)"
printf '\nFoxAir Updater bereit.\n'
printf 'Verzeichnis: %s\n' "$INSTALL_DIR"
printf 'Branch:      main\n'
printf 'Commit:      %s\n' "$commit"
printf '\nFirmware und Manifest hier ablegen:\n'
printf '  %s/firmware/\n' "$INSTALL_DIR"
printf '\nVom LTE-Modem geladene Backups landen hier:\n'
printf '  %s/downloaded_firmware/\n' "$INSTALL_DIR"
printf '\nUpdate-Logs und automatische DTU-Diagnosearchive landen hier:\n'
printf '  %s/logs/\n' "$INSTALL_DIR"
printf '\nStatus prüfen:\n'
printf '  cd %q\n' "$INSTALL_DIR"
printf '  ./foxair-updater status\n'
printf '\nFirmware/Diagnosedateien vom LTE-Modem sichern:\n'
printf '  ./foxair-updater download\n'
printf '\nAutonome Vorprüfung mit Manifest, z. B.:\n'
printf '  ./foxair-updater check FW3.5.json\n'
printf '\nAutonomes Firmwareupdate (interaktive Bestätigung):\n'
printf '  ./foxair-updater update FW3.5.json\n'
printf '\nRemotezugriff verwalten:\n'
printf '  ./foxair-updater remote status\n'
printf '  ./foxair-updater remote start|stop|enable|disable\n'
printf '\nWindows Remote-Modus: ADB TCP 5038; PHNIX-Debugstream TCP 5039 (read-only).\n'
printf 'Der Debug-Port wird automatisch über VID 1e0e / PID 9001 / Interface 04 erkannt.\n'
printf '\nFirmwaredateien und OTA-Zustände werden vom Installer selbst nicht heruntergeladen, verändert oder gelöscht.\n'
