#!/bin/sh
set -eu

REPO=${FOXAIR_FAKE_ADB_REPO:-dosordie/FoxAir_updater}
REF=${FOXAIR_FAKE_ADB_REF:-main}
RAW_BASE="https://raw.githubusercontent.com/$REPO/$REF"
INSTALL_DIR=${FOXAIR_FAKE_ADB_INSTALL_DIR:-/opt/foxair-fake-adb}
STATE_DIR=${FOXAIR_FAKE_ADB_STATE:-/var/lib/foxair-fake-adb}
CONFIG_FILE=/etc/default/foxair-fake-adb
SERVICE_FILE=/etc/systemd/system/foxair-fake-adb.service

if [ "$(id -u)" -ne 0 ]; then
    echo "Dieses Setup muss als root laufen. Beispiel:" >&2
    echo "  wget -qO- <URL>/install.sh | sudo sh" >&2
    exit 2
fi

need_cmd() {
    command -v "$1" >/dev/null 2>&1
}

if ! need_cmd wget || ! need_cmd python3 || ! need_cmd systemctl || ! need_cmd runuser; then
    if need_cmd apt-get; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        apt-get install -y --no-install-recommends wget ca-certificates python3 util-linux
    else
        echo "Benötigt: wget, python3, systemctl, runuser." >&2
        exit 2
    fi
fi

if ! id foxair-adb >/dev/null 2>&1; then
    useradd --system --home-dir "$STATE_DIR" --no-create-home --shell /usr/sbin/nologin foxair-adb
fi

install -d -m 0755 "$INSTALL_DIR"
install -d -o foxair-adb -g foxair-adb -m 0750 "$STATE_DIR"

fetch() {
    src=$1
    dst=$2
    echo "Lade $src"
    wget -q --https-only -O "$dst.tmp" "$RAW_BASE/$src"
    mv "$dst.tmp" "$dst"
}

fetch tools/testvm/fake_adb/foxair_fake_adb_server.py "$INSTALL_DIR/foxair_fake_adb_server.py"
fetch tools/phnix_ota/phnix_ota_simulator.py "$INSTALL_DIR/phnix_ota_simulator.py"
fetch tools/testvm/fake_adb/foxair-fake-adbctl "$INSTALL_DIR/foxair-fake-adbctl"
fetch tools/testvm/fake_adb/foxair-fake-adb.service "$SERVICE_FILE"

chmod 0755 "$INSTALL_DIR/foxair_fake_adb_server.py" "$INSTALL_DIR/phnix_ota_simulator.py" "$INSTALL_DIR/foxair-fake-adbctl"
ln -sf "$INSTALL_DIR/foxair-fake-adbctl" /usr/local/bin/foxair-fake-adbctl

if [ ! -f "$CONFIG_FILE" ]; then
    cat > "$CONFIG_FILE" <<EOF
# FoxAir Fake ADB – Lab/Testnetz only. Keine ADB-Authentifizierung.
FOXAIR_FAKE_ADB_BIND=0.0.0.0
FOXAIR_FAKE_ADB_PORT=5038
FOXAIR_FAKE_ADB_SERIAL=foxair-vm
FOXAIR_FAKE_ADB_STATE=$STATE_DIR
FOXAIR_FAKE_ADB_SIMULATOR=$INSTALL_DIR/phnix_ota_simulator.py
EOF
fi

chown -R foxair-adb:foxair-adb "$STATE_DIR"

# Initial simulator state. Do not destroy an existing test state on reinstall.
if [ ! -e "$STATE_DIR/simulator/started" ]; then
    install -d -o foxair-adb -g foxair-adb -m 0750 "$STATE_DIR/simulator"
    runuser -u foxair-adb -- env PHNIX_OTA_SIM_HOME="$STATE_DIR/simulator" \
        python3 "$INSTALL_DIR/phnix_ota_simulator.py" start --scenario success >/dev/null
fi

systemctl daemon-reload
systemctl enable --now foxair-fake-adb.service

# Fail installation if the service did not come up.
sleep 1
if ! systemctl is-active --quiet foxair-fake-adb.service; then
    systemctl --no-pager --full status foxair-fake-adb.service || true
    exit 1
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
PORT=$(awk -F= '$1=="FOXAIR_FAKE_ADB_PORT" {print $2}' "$CONFIG_FILE" | tail -1)
[ -n "$PORT" ] || PORT=5038

cat <<EOF

FoxAir Fake ADB wurde installiert.

Service:   foxair-fake-adb.service
Status:    sudo foxair-fake-adbctl status
Szenario:  sudo foxair-fake-adbctl scenario same-version
Logs:      sudo foxair-fake-adbctl logs

Windows FoxAir Updater:
  Remote ADB Server: EIN
  IP:   ${IP:-<VM-IP>}
  Port: $PORT

PowerShell-Test:
  \$env:ADB_SERVER_SOCKET="tcp:${IP:-<VM-IP>}:$PORT"
  adb.exe devices -l
  adb.exe get-state
  adb.exe shell "pidof phnixIot4G || true"

WICHTIG: Der Fake-ADB-Server hat absichtlich keine ADB-Authentifizierung.
Nur in einem isolierten/privaten Testnetz betreiben.
EOF
