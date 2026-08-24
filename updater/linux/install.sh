#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="https://github.com/dosordie/FoxAir_updater.git"
INSTALL_DIR="${FOX_AIR_INSTALL_DIR:-$HOME/FoxAir_updater}"
UDEV_RULE_FILE="/etc/udev/rules.d/51-foxair-android.rules"
UDEV_RULE='SUBSYSTEM=="usb", ATTR{idVendor}=="1e0e", ATTR{idProduct}=="9001", MODE="0666"'
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10

ok()   { printf '[OK] %s\n' "$*"; }
info() { printf '[..] %s\n' "$*"; }
warn() { printf '[WARNUNG] %s\n' "$*" >&2; }
die()  { printf '[FEHLER] %s\n' "$*" >&2; exit 1; }

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
elif [[ -d "$INSTALL_DIR" && -n "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    die "$INSTALL_DIR existiert bereits und ist kein FoxAir-Updater-Git-Repository."
else
    info "Lade FoxAir Updater nach $INSTALL_DIR"
    git clone --branch main --single-branch "$REPO_URL" "$INSTALL_DIR"
    git -C "$INSTALL_DIR" config core.fileMode false
    ok "Repository installiert"
fi

# Die Werkzeuge werden in der Dokumentation teils direkt aufgerufen. Die
# Ausführungsrechte werden lokal gesetzt; core.fileMode=false verhindert, dass
# dies spätere Updates als lokale Quellcodeänderung blockiert.
chmod 755 \
    "$INSTALL_DIR/tools/phnix_ota/phnix_local_ota_controller.py" \
    "$INSTALL_DIR/tools/phnix_ota/create_firmware_manifest.py" \
    "$INSTALL_DIR/tools/phnix_ota/phnix_ota_runtime_hook"
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

info "Prüfe FoxAir-Updater-Dateien"
(
    cd "$INSTALL_DIR"
    python3 tools/phnix_ota/phnix_local_ota_controller.py --help >/dev/null
    python3 tools/phnix_ota/create_firmware_manifest.py --help >/dev/null
)
ok "Python-Werkzeuge erfolgreich geprüft"

info "Starte ADB neu"
adb kill-server >/dev/null 2>&1 || true
adb start-server >/dev/null
ok "ADB-Server läuft"

adb_output="$(adb devices -l 2>&1 || true)"
printf '\n%s\n' "$adb_output"
if printf '%s\n' "$adb_output" | awk 'NR>1 && $2 == "device" {found=1} END {exit !found}'; then
    ok "ADB-Gerät erkannt"
else
    warn "Kein ADB-Gerät im Status 'device' erkannt. Die Installation ist trotzdem abgeschlossen. Modem anschließen und 'adb devices -l' erneut ausführen."
fi

commit="$(git -C "$INSTALL_DIR" rev-parse --short HEAD)"
printf '\nFoxAir Updater bereit.\n'
printf 'Verzeichnis: %s\n' "$INSTALL_DIR"
printf 'Branch:      main\n'
printf 'Commit:      %s\n' "$commit"
printf '\nStatusprüfung:\n'
printf '  cd %q\n' "$INSTALL_DIR"
printf '  python3 tools/phnix_ota/phnix_local_ota_controller.py --adb adb run --check status\n'
printf '\nFirmwaredateien und OTA-Zustände werden vom Installer nicht heruntergeladen, verändert oder gelöscht.\n'
