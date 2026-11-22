#!/usr/bin/env bash
# Run the original OTA flow in a private QEMU rootfs and network namespace.
set -euo pipefail
[[ $EUID == 0 ]] || exit 2
lab=${FOXAIR_QEMU_LAB_ROOT:-/opt/phnix-lab}
state=${FOXAIR_FAKE_ADB_STATE:-/var/lib/foxair-fake-adb}
case "${1:-}" in
  V1.0) image="$state/fixtures/phnixIot4G-v1.0"; profile=v10; old_at=1; signal_compat=0 ;;
  V1.2) image="$lab/rootfs/data/phnixIot4G"; profile=v12; old_at=0; signal_compat=1 ;;
  *) echo "Usage: $0 V1.0|V1.2" >&2; exit 2 ;;
esac
firmware="$lab/fixtures/phnixIot_device_OTA.v3.4"
[[ -f "$image" && -f "$firmware" ]] || { echo "Required lab fixture missing" >&2; exit 2; }
digest=97b4bb09bf854bd3c7521278de05354d9bb04a862dd05a864582b365d7af5890
printf '%s  %s\n' "$digest" "$firmware" | sha256sum -c

work=$(mktemp -d "$lab/native-ota-$profile.XXXXXX")
cleanup() { rm -rf -- "$work"; }
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
cp -a "$lab/rootfs" "$work/"
ln -s "$lab/tools" "$work/tools"
for dev in ttyGS0 ttyHSL2 smd8; do
  path="$work/rootfs/dev/$dev"
  if [[ -L "$path" ]]; then unlink "$path"; fi
  [[ ! -e "$path" ]] || { echo "Unexpected device in lab copy: $path" >&2; exit 2; }
done
rm -f -- "$work/rootfs/data/qmux_connect_socket" \
  "$work/rootfs/data/phnixIot_device_OTA_INFO" "$work/rootfs/cache/phnixIot_device_OTA"
install -m 0755 "$image" "$work/rootfs/data/phnixIot4G"

log_root="$lab/logs"
mkdir -p "$log_root"
echo "Start $1: logs under $log_root/native-ota-$profile-*"
env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LAB_ROOT="$work" LAB_LOG_ROOT="$log_root" \
  DTU_V10_AT_PROFILE="$old_at" LAB_QEMU_SIGFPE_COMPAT="$signal_compat" \
  RS485_STUB=1 QMUX_STUB=1 QMUX_INIT_PROFILE=1 \
  QMUX_CLIENT_ID=1 CREDENTIAL_STUB=1 MQTT_TLS_STUB=1 LOCAL_OTA_FULL_TRANSFER=1 \
  FIRMWARE_HTTP_ONLY=1 FIRMWARE_HTTP_FILE="$firmware" FIRMWARE_HTTP_SIZE=289806 \
  FIRMWARE_HTTP_MD5=149A586EDE6F035B385762EA48C71605 \
  LAB_OTA_OFFER_FILE="$lab/tools/ota_v34_lab_offer.json" \
  "$lab/tools/run_scenario_lab.sh" 2100 "native-ota-$profile"
