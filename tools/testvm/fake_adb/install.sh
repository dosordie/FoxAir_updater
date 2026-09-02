#!/bin/sh
set -eu

REPO=${FOXAIR_FAKE_ADB_REPO:-dosordie/FoxAir_updater}
REF=${FOXAIR_FAKE_ADB_REF:-VM_OTA_Simulator}
RAW_BASE="https://raw.githubusercontent.com/$REPO/$REF"
INSTALL_DIR=${FOXAIR_FAKE_ADB_INSTALL_DIR:-/opt/foxair-fake-adb}
STATE_DIR=${FOXAIR_FAKE_ADB_STATE:-/var/lib/foxair-fake-adb}
CONFIG_FILE=/etc/default/foxair-fake-adb
SERVICE_FILE=/etc/systemd/system/foxair-fake-adb.service
DEBUG_SERVICE_FILE=/etc/systemd/system/foxair-debug-stream.service
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
DEBUG_BIND=$(config_value FOXAIR_DEBUG_BIND "$BIND")
DEBUG_PORT=$(config_value FOXAIR_DEBUG_PORT 5039)
DEBUG_STATE=$(config_value FOXAIR_DEBUG_STREAM_STATE "$STATE_DIR/debug-stream.state")
SERIAL=$(config_value FOXAIR_FAKE_ADB_SERIAL foxair-vm)
LAB_ROOT=$(config_value FOXAIR_QEMU_LAB_ROOT "$DEFAULT_LAB_ROOT")
ROOTFS=$(config_value FOXAIR_QEMU_LAB_ROOTFS "$LAB_ROOT/rootfs")
SCENARIO_FILE=$(config_value FOXAIR_QEMU_SCENARIO_FILE "$LAB_ROOT/control/foxair-ota-scenario.json")
RUN_SECONDS=$(config_value FOXAIR_QEMU_RUN_SECONDS 3600)
case "$RUN_SECONDS" in
    ''|*[!0-9]*) echo "Ungültiges FOXAIR_QEMU_RUN_SECONDS=$RUN_SECONDS" >&2; exit 2 ;;
esac
if [ "$RUN_SECONDS" -lt 3600 ]; then
    echo "Erhöhe das alte Simulator-Zeitfenster von ${RUN_SECONDS}s auf 3600s."
    RUN_SECONDS=3600
fi
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
fetch tools/testvm/fake_adb/foxair_debug_stream_server.py "$INSTALL_DIR/foxair_debug_stream_server.py"
fetch tools/testvm/fake_adb/qemu_lab_adapter.py "$INSTALL_DIR/qemu_lab_adapter.py"
fetch tools/testvm/fake_adb/qemu_work_lab_backend.py "$INSTALL_DIR/qemu_work_lab_backend.py"
fetch tools/testvm/fake_adb/qemu_permissive_backend.py "$INSTALL_DIR/qemu_permissive_backend.py"
fetch tools/testvm/fake_adb/gdb_warm_detach.gdb "$INSTALL_DIR/gdb_warm_detach.gdb"
fetch tools/testvm/fake_adb/gdb_original_ota_1fe40.gdb "$INSTALL_DIR/gdb_original_ota_1fe40.gdb"
fetch tools/testvm/work_lab/run_scenario_lab.sh "$LAB_ROOT/tools/run_scenario_lab.sh"
fetch tools/testvm/work_lab/rs485_fault_emulator.py "$LAB_ROOT/tools/rs485_fault_emulator.py"
fetch tools/testvm/work_lab/mqtt_scenario_stub.py "$LAB_ROOT/tools/mqtt_scenario_stub.py"
fetch tools/testvm/work_lab/qmux_stub.py "$LAB_ROOT/tools/qmux_stub.py"
fetch tools/testvm/work_lab/credential_http_stub.py "$LAB_ROOT/tools/credential_http_stub.py"
fetch tools/testvm/work_lab/prepare_tls_lab.py "$LAB_ROOT/tools/prepare_tls_lab.py"
# Re-use only the deterministic OTA hook state machine from the repository.
# qemu_permissive_backend.py remaps all of its remote file access back into the
# existing Work-QEMU/ADB namespace; this does NOT create a second modem rootfs.
fetch tools/phnix_ota/phnix_ota_simulator.py "$INSTALL_DIR/phnix_ota_simulator.py"
fetch tools/testvm/fake_adb/foxair-fake-adbctl "$INSTALL_DIR/foxair-fake-adbctl"
fetch tools/testvm/fake_adb/foxair-fake-adb.service "$SERVICE_FILE"
fetch tools/testvm/fake_adb/foxair-debug-stream.service "$DEBUG_SERVICE_FILE"

# These files belonged to older simulator layouts.  They are never valid
# runtime sources after a reinstall and must not mask the branch contents.
rm -f "$INSTALL_DIR/dtu_ota_supervisor.sh" \
    "$INSTALL_DIR/phnix_ota_runtime_hook" \
    "$INSTALL_DIR/qemu_work_lab_backend.py.tmp" \
    "$INSTALL_DIR/qemu_permissive_backend.py.tmp"
rm -rf "$INSTALL_DIR/__pycache__"

python3 -m py_compile \
    "$INSTALL_DIR/foxair_fake_adb_server.py" \
    "$INSTALL_DIR/foxair_debug_stream_server.py" \
    "$INSTALL_DIR/qemu_lab_adapter.py" \
    "$INSTALL_DIR/qemu_work_lab_backend.py" \
    "$INSTALL_DIR/qemu_permissive_backend.py" \
    "$INSTALL_DIR/phnix_ota_simulator.py"
sh -n "$LAB_ROOT/tools/run_scenario_lab.sh"

chmod 0755 \
    "$INSTALL_DIR/foxair_fake_adb_server.py" \
    "$INSTALL_DIR/foxair_debug_stream_server.py" \
    "$INSTALL_DIR/qemu_lab_adapter.py" \
    "$INSTALL_DIR/qemu_work_lab_backend.py" \
    "$INSTALL_DIR/qemu_permissive_backend.py" \
    "$INSTALL_DIR/phnix_ota_simulator.py" \
    "$INSTALL_DIR/foxair-fake-adbctl"
chmod 0755 "$LAB_ROOT/tools/run_scenario_lab.sh" "$LAB_ROOT/tools/rs485_fault_emulator.py" \
    "$LAB_ROOT/tools/mqtt_scenario_stub.py" "$LAB_ROOT/tools/qmux_stub.py" \
    "$LAB_ROOT/tools/credential_http_stub.py" "$LAB_ROOT/tools/prepare_tls_lab.py"
ln -sf "$INSTALL_DIR/foxair-fake-adbctl" /usr/local/bin/foxair-fake-adbctl

if [ -d "$STATE_DIR/simulator" ] && [ ! -e "$STATE_DIR/legacy-python-simulator" ]; then
    mv "$STATE_DIR/simulator" "$STATE_DIR/legacy-python-simulator"
fi

cat > "$CONFIG_FILE" <<EOF
FOXAIR_FAKE_ADB_BIND=$BIND
FOXAIR_FAKE_ADB_PORT=$PORT
FOXAIR_DEBUG_BIND=$DEBUG_BIND
FOXAIR_DEBUG_PORT=$DEBUG_PORT
FOXAIR_DEBUG_LOGS_ROOT=$LAB_ROOT/logs
FOXAIR_DEBUG_STREAM_STATE=$DEBUG_STATE
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
install -d -m 0750 "$STATE_DIR/runtime-sim"
touch "$STATE_DIR/qemu-adb/started"
if [ ! -e "$DEBUG_STATE" ]; then
    printf 'on\n' > "$DEBUG_STATE"
fi

systemctl daemon-reload
systemctl enable --now foxair-fake-adb.service
systemctl restart foxair-fake-adb.service
systemctl enable --now foxair-debug-stream.service
systemctl restart foxair-debug-stream.service

sleep 1
if ! systemctl is-active --quiet foxair-fake-adb.service; then
    systemctl --no-pager --full status foxair-fake-adb.service || true
    exit 1
fi
if ! systemctl is-active --quiet foxair-debug-stream.service; then
    systemctl --no-pager --full status foxair-debug-stream.service || true
    exit 1
fi

if ! "$INSTALL_DIR/foxair-fake-adbctl" scenario success; then
    echo "Standard-QEMU-Szenario konnte nicht gestartet werden." >&2
    "$INSTALL_DIR/foxair-fake-adbctl" status || true
    exit 1
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
SERVICE_SIZE=$(wc -c < "$ROOTFS/data/phnixIot4G" | tr -d ' ')
SERVICE_SHA=$(sha256sum "$ROOTFS/data/phnixIot4G" | awk '{print $1}')

cat <<EOF

FoxAir Fake ADB ist installiert und das normale success/original-QEMU-Szenario läuft.

ADB-Service:   foxair-fake-adb.service
Debug-Service: foxair-debug-stream.service (TCP $DEBUG_PORT)
QEMU-Lab:      $LAB_ROOT
QEMU-RootFS:   $ROOTFS
ADB /data:     -> $ROOTFS/data
ADB /cache:    -> $ROOTFS/cache
ADB /tmp:      -> $DEVICE_TMP
Debian-Pfade:  /data, /cache und /tmp werden nicht global umgebogen
Runtime-Hook:  deterministische Test-Zustandsmaschine auf denselben ADB/QEMU-Dateien
phnixIot4G:    $SERVICE_SIZE Byte
SHA-256:       $SERVICE_SHA

Windows:
  \$env:ADB_SERVER_SOCKET="tcp:${IP:-<VM-IP>}:$PORT"
  adb.exe devices -l
  adb.exe shell "pidof phnixIot4G || true"
  adb.exe shell "df -k /data 2>/dev/null"
  Debugstream: TCP ${IP:-<VM-IP>}:$DEBUG_PORT
EOF
