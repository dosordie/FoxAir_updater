#!/bin/sh
set -eu

REPO=${FOXAIR_FAKE_ADB_REPO:-dosordie/FoxAir_updater}
REF=${FOXAIR_FAKE_ADB_REF:-main}
RAW_BASE="https://raw.githubusercontent.com/$REPO/$REF"
INSTALL_DIR=${FOXAIR_FAKE_ADB_INSTALL_DIR:-/opt/foxair-fake-adb}
STATE_DIR=${FOXAIR_FAKE_ADB_STATE:-/var/lib/foxair-fake-adb}
CONFIG_FILE=/etc/default/foxair-fake-adb
SERVICE_FILE=/etc/systemd/system/foxair-fake-adb.service
DEFAULT_LAB_ROOT=${FOXAIR_QEMU_LAB_ROOT:-/opt/phnix-lab}

if [ "$(id -u)" -ne 0 ]; then
    echo "Dieses Setup muss als root laufen. Beispiel:" >&2
    echo "  wget -qO- <URL>/install.sh | sudo sh" >&2
    exit 2
fi

need_cmd() {
    command -v "$1" >/dev/null 2>&1
}

if ! need_cmd wget || ! need_cmd python3 || ! need_cmd systemctl; then
    if need_cmd apt-get; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        apt-get install -y --no-install-recommends wget ca-certificates python3
    else
        echo "Benötigt: wget, python3 und systemctl." >&2
        exit 2
    fi
fi

config_value() {
    key=$1
    fallback=$2
    if [ -f "$CONFIG_FILE" ]; then
        value=$(sed -n "s/^${key}=//p" "$CONFIG_FILE" | tail -1)
        if [ -n "$value" ]; then
            printf '%s\n' "$value"
            return
        fi
    fi
    printf '%s\n' "$fallback"
}

BIND=$(config_value FOXAIR_FAKE_ADB_BIND 0.0.0.0)
PORT=$(config_value FOXAIR_FAKE_ADB_PORT 5038)
SERIAL=$(config_value FOXAIR_FAKE_ADB_SERIAL foxair-vm)
LAB_ROOT=$(config_value FOXAIR_QEMU_LAB_ROOT "$DEFAULT_LAB_ROOT")
ROOTFS=$(config_value FOXAIR_QEMU_LAB_ROOTFS "$LAB_ROOT/rootfs")
SCENARIO_FILE=$(config_value FOXAIR_QEMU_SCENARIO_FILE "$LAB_ROOT/control/foxair-ota-scenario.json")
RUN_SECONDS=$(config_value FOXAIR_QEMU_RUN_SECONDS 1200)

if [ ! -f "$ROOTFS/data/phnixIot4G" ]; then
    for candidate in "$LAB_ROOT/rootfs" "$LAB_ROOT/root" "$LAB_ROOT/chroot"; do
        if [ -f "$candidate/data/phnixIot4G" ]; then
            ROOTFS=$candidate
            break
        fi
    done
fi
if [ ! -f "$ROOTFS/data/phnixIot4G" ]; then
    echo "PHNIX-QEMU-RootFS nicht gefunden." >&2
    echo "Erwartet: $LAB_ROOT/rootfs/data/phnixIot4G" >&2
    exit 2
fi

for path in \
    "$ROOTFS/usr/bin/qemu-arm-static" \
    "$LAB_ROOT/tools/run_scenario_lab.sh" \
    "$LAB_ROOT/tools/rs485_fault_emulator.py"; do
    if [ ! -e "$path" ]; then
        echo "Work-QEMU-Lab unvollständig, fehlt: $path" >&2
        exit 2
    fi
done

install -d -m 0755 "$INSTALL_DIR"
install -d -m 0750 "$STATE_DIR"
install -d -m 0755 "$LAB_ROOT/control"

fetch() {
    src=$1
    dst=$2
    echo "Lade $src"
    wget -q --https-only -O "$dst.tmp" "$RAW_BASE/$src"
    mv "$dst.tmp" "$dst"
}

fetch tools/testvm/fake_adb/foxair_fake_adb_server.py "$INSTALL_DIR/foxair_fake_adb_server.py"
fetch tools/testvm/fake_adb/qemu_lab_adapter.py "$INSTALL_DIR/qemu_lab_adapter.py"
fetch tools/testvm/fake_adb/qemu_work_lab_backend.py "$INSTALL_DIR/qemu_work_lab_backend.py"
fetch tools/testvm/fake_adb/foxair-fake-adbctl "$INSTALL_DIR/foxair-fake-adbctl"
fetch tools/testvm/fake_adb/foxair-fake-adb.service "$SERVICE_FILE"

chmod 0755 \
    "$INSTALL_DIR/foxair_fake_adb_server.py" \
    "$INSTALL_DIR/qemu_lab_adapter.py" \
    "$INSTALL_DIR/qemu_work_lab_backend.py" \
    "$INSTALL_DIR/foxair-fake-adbctl"
ln -sf "$INSTALL_DIR/foxair-fake-adbctl" /usr/local/bin/foxair-fake-adbctl

if [ -d "$STATE_DIR/simulator" ] && [ ! -e "$STATE_DIR/legacy-python-simulator" ]; then
    mv "$STATE_DIR/simulator" "$STATE_DIR/legacy-python-simulator"
fi
rm -f "$INSTALL_DIR/phnix_ota_simulator.py"

cat > "$CONFIG_FILE" <<EOF
# FoxAir Fake ADB – Lab/Testnetz only. Keine ADB-Authentifizierung.
FOXAIR_FAKE_ADB_BIND=$BIND
FOXAIR_FAKE_ADB_PORT=$PORT
FOXAIR_FAKE_ADB_SERIAL=$SERIAL
FOXAIR_FAKE_ADB_STATE=$STATE_DIR
FOXAIR_FAKE_ADB_SIMULATOR=$INSTALL_DIR/qemu_work_lab_backend.py
FOXAIR_QEMU_LAB_ROOT=$LAB_ROOT
FOXAIR_QEMU_LAB_ROOTFS=$ROOTFS
FOXAIR_QEMU_SCENARIO_FILE=$SCENARIO_FILE
FOXAIR_QEMU_RUN_SECONDS=$RUN_SECONDS
EOF

install -d -m 0750 "$STATE_DIR/qemu-adb"
touch "$STATE_DIR/qemu-adb/started"

systemctl daemon-reload
systemctl enable --now foxair-fake-adb.service
systemctl restart foxair-fake-adb.service

sleep 1
if ! systemctl is-active --quiet foxair-fake-adb.service; then
    systemctl --no-pager --full status foxair-fake-adb.service || true
    exit 1
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
SERVICE_SIZE=$(wc -c < "$ROOTFS/data/phnixIot4G" | tr -d ' ')
SERVICE_SHA=$(sha256sum "$ROOTFS/data/phnixIot4G" | awk '{print $1}')

cat <<EOF

FoxAir Fake ADB verwendet jetzt direkt das vorhandene Work-QEMU-Lab.

ADB-Service:   foxair-fake-adb.service
QEMU-Lab:      $LAB_ROOT
QEMU-RootFS:   $ROOTFS
phnixIot4G:    $SERVICE_SIZE Byte
SHA-256:       $SERVICE_SHA
Lab-Runner:    $LAB_ROOT/tools/run_scenario_lab.sh
RS485-Faker:   $LAB_ROOT/tools/rs485_fault_emulator.py

Vor einem Status-/Preflight-Test bitte ein QEMU-Szenario starten, z. B.:
  sudo foxair-fake-adbctl scenario same-version

Danach prüfen:
  sudo foxair-fake-adbctl status

Windows:
  \$env:ADB_SERVER_SOCKET="tcp:${IP:-<VM-IP>}:$PORT"
  adb.exe devices -l
  adb.exe shell "pidof phnixIot4G || true"
  adb.exe pull /data/phnixIot4G phnixIot4G-from-qemu

WICHTIG: Port 5038 besitzt absichtlich keine ADB-Authentifizierung.
Nur in einem isolierten/privaten Testnetz verwenden.
EOF
