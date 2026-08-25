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

if ! need_cmd apt-get; then
    echo "Dieses Setup erwartet Debian/Ubuntu mit apt-get." >&2
    exit 2
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
    wget ca-certificates python3 busybox curl gdb net-tools iproute2 procps bubblewrap

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
DEVICE_TMP=$(config_value FOXAIR_FAKE_ADB_TMP "$STATE_DIR/device-tmp")

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

install -d -m 0755 "$ROOTFS/data" "$ROOTFS/cache" "$ROOTFS/tmp"
install -d -m 0755 "$INSTALL_DIR"
install -d -m 0750 "$STATE_DIR"
install -d -m 1777 "$DEVICE_TMP"
install -d -m 0755 "$LAB_ROOT/control"

# Older PR revisions exposed QEMU /data and /cache as global Debian symlinks.
# Remove only those links if they still point at this Work rootfs. Real host
# directories are never touched; ADB overlays the device paths privately.
remove_legacy_link() {
    path=$1
    expected=$2
    if [ ! -L "$path" ]; then
        return
    fi
    resolved=$(readlink -f "$path" 2>/dev/null || true)
    expected_resolved=$(readlink -f "$expected" 2>/dev/null || printf '%s' "$expected")
    if [ "$resolved" = "$expected_resolved" ]; then
        echo "Entferne alten globalen ADB-Link $path -> $resolved"
        rm -f "$path"
        return
    fi
    echo "$path ist ein fremder Symlink ($resolved); wird nicht verändert." >&2
    echo "Bitte manuell klären, bevor Fake-ADB gestartet wird." >&2
    exit 2
}
remove_legacy_link /data "$ROOTFS/data"
remove_legacy_link /cache "$ROOTFS/cache"

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
fetch tools/testvm/fake_adb/qemu_permissive_backend.py "$INSTALL_DIR/qemu_permissive_backend.py"
fetch tools/testvm/fake_adb/foxair-fake-adbctl "$INSTALL_DIR/foxair-fake-adbctl"
fetch tools/testvm/fake_adb/foxair-fake-adb.service "$SERVICE_FILE"

chmod 0755 \
    "$INSTALL_DIR/foxair_fake_adb_server.py" \
    "$INSTALL_DIR/qemu_lab_adapter.py" \
    "$INSTALL_DIR/qemu_work_lab_backend.py" \
    "$INSTALL_DIR/qemu_permissive_backend.py" \
    "$INSTALL_DIR/foxair-fake-adbctl"
ln -sf "$INSTALL_DIR/foxair-fake-adbctl" /usr/local/bin/foxair-fake-adbctl

if [ -d "$STATE_DIR/simulator" ] && [ ! -e "$STATE_DIR/legacy-python-simulator" ]; then
    mv "$STATE_DIR/simulator" "$STATE_DIR/legacy-python-simulator"
fi
rm -f "$INSTALL_DIR/phnix_ota_simulator.py"

cat > "$CONFIG_FILE" <<EOF
# FoxAir Fake ADB – dedicated TestVM, intentionally unrestricted root shell.
FOXAIR_FAKE_ADB_BIND=$BIND
FOXAIR_FAKE_ADB_PORT=$PORT
FOXAIR_FAKE_ADB_SERIAL=$SERIAL
FOXAIR_FAKE_ADB_STATE=$STATE_DIR
FOXAIR_FAKE_ADB_TMP=$DEVICE_TMP
FOXAIR_FAKE_ADB_SIMULATOR=$INSTALL_DIR/qemu_permissive_backend.py
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

FoxAir Fake ADB verwendet das vorhandene Work-QEMU-Lab mit einer
absichtlich uneingeschränkten Debian-root-ADB-Shell.

ADB-Service:   foxair-fake-adb.service
QEMU-Lab:      $LAB_ROOT
QEMU-RootFS:   $ROOTFS
ADB /data:     -> $ROOTFS/data (nur im ADB-Mount-Namespace)
ADB /cache:    -> $ROOTFS/cache (nur im ADB-Mount-Namespace)
ADB /tmp:      -> $DEVICE_TMP (nur im ADB-Mount-Namespace)
Debian-Pfade:  /data, /cache und /tmp werden nicht umgebogen
phnixIot4G:    $SERVICE_SIZE Byte
SHA-256:       $SERVICE_SHA

Installierte Shell-Werkzeuge: busybox, curl, gdb, netstat, ss, ps, bubblewrap

Vor einem Status-/Preflight-Test ein QEMU-Szenario starten, z. B.:
  sudo foxair-fake-adbctl scenario same-version

Windows:
  \$env:ADB_SERVER_SOCKET="tcp:${IP:-<VM-IP>}:$PORT"
  adb.exe devices -l
  adb.exe shell "id"
  adb.exe shell "ls -l /data/phnixIot4G"
  adb.exe shell "echo test >/tmp/adb-only && cat /tmp/adb-only"

Hinweis: Jeder ADB-shell-Befehl wird als root ausgeführt, aber die drei
modemkritischen Pfade /data, /cache und /tmp sind vom Debian-Host getrennt.
EOF
