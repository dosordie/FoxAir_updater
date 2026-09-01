#!/usr/bin/env bash
set -Eeuo pipefail

LAB_ROOT="${LAB_ROOT:-/opt/phnix-lab}"
ROOTFS="$LAB_ROOT/rootfs"
TOOLS="$LAB_ROOT/tools"
RUN_SECS="${1:-35}"
LABEL="${2:-at-emulator}"
STAMP="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="$LAB_ROOT/logs/${LABEL}-${STAMP}"
MQTT_HOST="a1LABTEST01.iot-as-mqtt.eu-central-1.aliyuncs.com"
TLS_DIR="$LAB_ROOT/state/tls"
V33_FIXTURE="$LAB_ROOT/fixtures/phnixIot_device_OTA.v3.3"

if [[ "${V33_FULL_TRANSFER:-0}" == 1 ]]; then
  export V33_DOWNLOAD_PROBE=1
fi

fail() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }
[[ ${EUID} -eq 0 ]] || fail "run as root: sudo $0 [seconds] [label]"
[[ "$RUN_SECS" =~ ^[0-9]+$ ]] || fail "seconds must be numeric"
(( RUN_SECS >= 5 && RUN_SECS <= 3600 )) || fail "seconds must be 5..3600"
for path in "$ROOTFS/data/phnixIot4G" "$ROOTFS/usr/bin/qemu-arm-static" \
            "$TOOLS/at_emulator.py" "$TOOLS/at_rules.json"; do
  [[ -e "$path" ]] || fail "missing: $path"
done
for command in unshare socat timeout xxd python3 ip; do
  command -v "$command" >/dev/null || fail "missing command: $command"
done

if [[ "${MQTT_TLS_STUB:-0}" == 1 ]]; then
  for path in "$TOOLS/mqtt_scenario_stub.py" "$TOOLS/prepare_tls_lab.py"; do
    [[ -e "$path" ]] || fail "missing: $path"
  done
  command -v openssl >/dev/null || fail "missing command: openssl"
  install -d -m 0700 "$TLS_DIR"
  if [[ ! -s "$TLS_DIR/ca.pem" || ! -s "$TLS_DIR/server.pem" || ! -s "$TLS_DIR/server.key" ]]; then
    rm -f "$TLS_DIR/ca.key" "$TLS_DIR/ca.pem" "$TLS_DIR/ca.srl" \
          "$TLS_DIR/server.key" "$TLS_DIR/server.csr" "$TLS_DIR/server.pem" "$TLS_DIR/server.ext"
    openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 30 \
      -subj '/CN=PHNIX isolated lab CA' \
      -keyout "$TLS_DIR/ca.key" -out "$TLS_DIR/ca.pem" >/dev/null 2>&1
    openssl req -newkey rsa:2048 -nodes -sha256 -subj "/CN=$MQTT_HOST" \
      -keyout "$TLS_DIR/server.key" -out "$TLS_DIR/server.csr" >/dev/null 2>&1
    printf 'subjectAltName=DNS:%s\nextendedKeyUsage=serverAuth\n' "$MQTT_HOST" > "$TLS_DIR/server.ext"
    openssl x509 -req -sha256 -days 30 -in "$TLS_DIR/server.csr" \
      -CA "$TLS_DIR/ca.pem" -CAkey "$TLS_DIR/ca.key" -CAcreateserial \
      -extfile "$TLS_DIR/server.ext" -out "$TLS_DIR/server.pem" >/dev/null 2>&1
    chmod 0600 "$TLS_DIR"/*.key
  fi
  python3 "$TOOLS/prepare_tls_lab.py" \
    --source "$ROOTFS/data/phnixIot4G" \
    --output "$ROOTFS/data/phnixIot4G.tls-lab" \
    --ca "$TLS_DIR/ca.pem"
fi
if [[ "${OTA_0033_PARSE_PROBE:-0}" == 1 ]]; then
  [[ "${MQTT_TLS_STUB:-0}" == 1 ]] || fail "OTA_0033_PARSE_PROBE requires MQTT_TLS_STUB=1"
  [[ -f "$TOOLS/gdb_ota_0033_parse_probe.gdb" ]] || fail "missing 0033 GDB guard"
  [[ -f "$TOOLS/ota_0033_parse_probe.json" ]] || fail "missing 0033 probe payload"
  command -v gdb-multiarch >/dev/null || fail "missing command: gdb-multiarch"
fi
if [[ "${V33_DOWNLOAD_PROBE:-0}" == 1 ]]; then
  [[ "${MQTT_TLS_STUB:-0}" == 1 ]] || fail "V33_DOWNLOAD_PROBE requires MQTT_TLS_STUB=1"
  [[ -f "$V33_FIXTURE" ]] || fail "missing V3.3 fixture: $V33_FIXTURE"
  [[ -f "$TOOLS/firmware_http_stub.py" ]] || fail "missing firmware HTTP stub"
  [[ -f "$TOOLS/ota_0033_v33_download_probe.json" ]] || fail "missing V3.3 0033 payload"
  [[ -f "$TOOLS/gdb_v33_before_rs485.gdb" ]] || fail "missing pre-RS485 GDB guard"
  command -v gdb-multiarch >/dev/null || fail "missing command: gdb-multiarch"
fi
if [[ "${LOCAL_OTA_HANDLER:-0}" == 1 ]]; then
  [[ -f "$V33_FIXTURE" ]] || fail "missing V3.3 fixture: $V33_FIXTURE"
  [[ -f "$TOOLS/firmware_http_stub.py" ]] || fail "missing firmware HTTP stub"
  [[ -f "$TOOLS/gdb_local_ota_handler.gdb" ]] || fail "missing local OTA handler GDB script"
  if [[ "${LOCAL_OTA_HANDLER_LATE:-0}" == 1 ]]; then
    [[ -f "$TOOLS/gdb_local_ota_handler_late.gdb" ]] || fail "missing late local OTA handler GDB script"
  fi
  command -v gdb-multiarch >/dev/null || fail "missing command: gdb-multiarch"
fi
if [[ "${V33_FULL_TRANSFER:-0}" == 1 ]]; then
  [[ -f "$TOOLS/gdb_v33_full_transfer.gdb" ]] || fail "missing full-transfer GDB guard"
fi

install -d -m 0755 "$RUN_DIR" "$ROOTFS/dev" "$ROOTFS/dev/pts"
for device in ttyGS0 smd8 ttyHSL2; do
  [[ ! -e "$ROOTFS/dev/$device" && ! -L "$ROOTFS/dev/$device" ]] ||
    fail "$ROOTFS/dev/$device already exists"
done
cp "$TOOLS/at_rules.json" "$RUN_DIR/at_rules.json"

set +e
unshare --net --mount --fork bash -c '
  set -Eeuo pipefail
  rootfs="$1"; tools="$2"; run_dir="$3"; run_secs="$4"; tls_dir="$5"; mqtt_host="$6"; v33_fixture="$7"
  cleanup() {
    set +e
    for pid in "${firmware_pid:-}" "${mqtt_pid:-}" "${credential_pid:-}" "${qmux_pid:-}" "${rs485_pid:-}" \
               "${emu_pid:-}" "${cat_gs0:-}" \
               "${soc_gs0:-}" "${soc_smd8:-}" "${soc_hsl2:-}"; do
      [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
    done
    rm -f "$rootfs/dev/ttyGS0" "$rootfs/dev/smd8" "$rootfs/dev/ttyHSL2"
    rm -f "$rootfs/data/qmux_connect_socket"
    umount "$rootfs/etc/hosts" 2>/dev/null || true
    umount "$rootfs/dev/pts" 2>/dev/null || true
  }
  trap cleanup EXIT INT TERM
  mount --make-rprivate /
  mount --bind /dev/pts "$rootfs/dev/pts"
  ip link set lo up
  if ip route show default | grep -q . || ip -6 route show default | grep -q .; then
    echo "unexpected default route in test namespace" >&2
    exit 90
  fi
  ip addr show > "$run_dir/network.txt"

  if [[ "${CREDENTIAL_STUB:-0}" == 1 ]]; then
    [[ -x "$tools/credential_http_stub.py" ]] || {
      echo "credential_http_stub.py missing" >&2; exit 96;
    }
    cp "$rootfs/etc/hosts" "$run_dir/hosts"
    printf "\n127.0.0.1 cloud.linked-go.com\n" >> "$run_dir/hosts"
    mount --bind "$run_dir/hosts" "$rootfs/etc/hosts"
    python3 "$tools/credential_http_stub.py" \
      --transcript "$run_dir/credential-http-transcript.jsonl" &
    credential_pid=$!
  fi

  if [[ "${MQTT_TLS_STUB:-0}" == 1 ]]; then
    [[ -x "$tools/mqtt_scenario_stub.py" ]] || {
      echo "mqtt_scenario_stub.py missing" >&2; exit 97;
    }
    if [[ "${CREDENTIAL_STUB:-0}" != 1 ]]; then
      cp "$rootfs/etc/hosts" "$run_dir/hosts"
      mount --bind "$run_dir/hosts" "$rootfs/etc/hosts"
    fi
    printf "127.0.0.1 %s\n" "$mqtt_host" >> "$run_dir/hosts"
    mqtt_args=(
      --cert "$tls_dir/server.pem" --key "$tls_dir/server.key"
      --transcript "$run_dir/mqtt-tls-transcript.jsonl"
      --binary-log "$run_dir/mqtt-from-client.bin"
      --control-socket "$run_dir/mqtt-control.sock"
    )
    if [[ "${NORMAL_GET_PROBE:-0}" == 1 ]]; then
      # Deliberately invalid as Modbus: recognizable lab-only bytes "LAB-PROBE".
      mqtt_args+=(--probe-topic "/a1LABTEST01/LABDEVICE001/user/get"
                  --probe-payload-hex 4c41422d50524f4245)
    elif [[ "${OTA_0033_PARSE_PROBE:-0}" == 1 ]]; then
      mqtt_args+=(--probe-topic "/a1LABTEST01/LABDEVICE001/user/OTA_GET"
                  --probe-payload-file "$tools/ota_0033_parse_probe.json")
    elif [[ "${V33_DOWNLOAD_PROBE:-0}" == 1 ]]; then
      mqtt_args+=(--probe-topic "/a1LABTEST01/LABDEVICE001/user/OTA_GET"
                  --probe-payload-file "${PROBE_PAYLOAD_FILE:-$tools/ota_0033_v33_download_probe.json}")
    fi
    if [[ -n "${SECOND_PROBE_SPEC:-}" ]]; then
      mqtt_args+=(--scheduled-probe "$SECOND_PROBE_SPEC")
    fi
    python3 "$tools/mqtt_scenario_stub.py" \
      "${mqtt_args[@]}" &
    mqtt_pid=$!
  fi

  if [[ "${V33_DOWNLOAD_PROBE:-0}" == 1 || "${LOCAL_OTA_HANDLER:-0}" == 1 ]]; then
    firmware_file="$v33_fixture"
    firmware_size=287598
    firmware_md5=CEB6A4BF386FF644E23E410023E74673
    if [[ "${DYNAMIC_LOCAL_OTA:-0}" == 1 ]]; then
      firmware_file="$rootfs/data/phnix_local_ota/phnixIot_device_OTA.bin"
      [[ -f "$firmware_file" ]] || {
        echo "staged local OTA firmware missing: $firmware_file" >&2
        exit 96
      }
      firmware_size="$(wc -c < "$firmware_file" | tr -d " ")"
      firmware_md5="$(md5sum "$firmware_file" | cut -d " " -f 1 | tr "[:lower:]" "[:upper:]")"
    fi
    python3 "$tools/firmware_http_stub.py" \
      --firmware "$firmware_file" \
      --transcript "$run_dir/firmware-http-transcript.jsonl" \
      --expected-size "$firmware_size" \
      --expected-md5 "$firmware_md5" &
    firmware_pid=$!
  fi

  socat -d -d PTY,raw,echo=0,link="$rootfs/dev/ttyGS0" \
    PTY,raw,echo=0,link="$run_dir/ttyGS0.peer" 2> "$run_dir/socat-ttyGS0.log" &
  soc_gs0=$!
  socat -d -d PTY,raw,echo=0,link="$rootfs/dev/smd8" \
    PTY,raw,echo=0,link="$run_dir/smd8.peer" 2> "$run_dir/socat-smd8.log" &
  soc_smd8=$!
  if [[ "${RS485_STUB:-0}" == 1 ]]; then
    [[ -x "$tools/rs485_fault_emulator.py" ]] || {
      echo "rs485_fault_emulator.py missing" >&2; exit 95;
    }
    socat -d -d PTY,raw,echo=0,link="$rootfs/dev/ttyHSL2" \
      PTY,raw,echo=0,link="$run_dir/ttyHSL2.peer" 2> "$run_dir/socat-ttyHSL2.log" &
    soc_hsl2=$!
  fi
  for _ in $(seq 1 30); do
    [[ -L "$rootfs/dev/ttyGS0" && -L "$rootfs/dev/smd8" &&
       -L "$run_dir/ttyGS0.peer" && -L "$run_dir/smd8.peer" ]] && break
    sleep 0.1
  done
  [[ -L "$rootfs/dev/ttyGS0" && -L "$rootfs/dev/smd8" ]] || exit 92

  if [[ "${RS485_STUB:-0}" == 1 ]]; then
    for _ in $(seq 1 30); do
      [[ -L "$rootfs/dev/ttyHSL2" && -L "$run_dir/ttyHSL2.peer" ]] && break
      sleep 0.1
    done
    [[ -L "$rootfs/dev/ttyHSL2" && -L "$run_dir/ttyHSL2.peer" ]] || exit 95
    rs485_args=(
      --peer "$run_dir/ttyHSL2.peer"
      --from-app "$run_dir/ttyHSL2-from-app.bin"
      --to-app "$run_dir/ttyHSL2-to-app.bin"
      --transcript "$run_dir/ttyHSL2-transcript.txt"
    )
    if [[ "${V33_FULL_TRANSFER:-0}" == 1 || "${LOCAL_OTA_FULL_TRANSFER:-0}" == 1 ]]; then
      rs485_args+=(
        --v33-full-transfer
        --firmware "$rootfs/data/phnix_local_ota/phnixIot_device_OTA.bin"
        --board-version "${BOARD_VERSION:-0033}"
        --timing-profile "${OTA_TIMING_PROFILE:-fast}"
      )
    elif [[ "${V33_DOWNLOAD_PROBE:-0}" == 1 || "${LOCAL_OTA_HANDLER:-0}" == 1 ]]; then
      rs485_args+=(--v33-ota-handshake)
    fi
    rs485_args+=(--fault-scenario "${FAULT_SCENARIO:-success}")
    if [[ -n "${BOARD_RESUME_STATE:-}" ]]; then
      rs485_args+=(--resume-state "${BOARD_RESUME_STATE}")
    fi
    if [[ "${CANCEL_ACK:-0}" == 1 ]]; then
      rs485_args+=(--cancel-ack)
    fi
    python3 "$tools/rs485_fault_emulator.py" "${rs485_args[@]}" &
    rs485_pid=$!
  fi

  cat "$run_dir/ttyGS0.peer" > "$run_dir/ttyGS0-from-app.bin" &
  cat_gs0=$!
  python3 "$tools/at_emulator.py" \
    --peer "$run_dir/smd8.peer" --rules "$tools/at_rules.json" \
    --from-app "$run_dir/smd8-from-app.bin" --to-app "$run_dir/smd8-to-app.bin" \
    --transcript "$run_dir/smd8-transcript.txt" --unknown "$run_dir/unknown-at.txt" &
  emu_pid=$!

  if [[ "${QMUX_STUB:-0}" == 1 ]]; then
    [[ -x "$tools/qmux_stub.py" ]] || { echo "qmux_stub.py missing" >&2; exit 93; }
    qmux_args=(
      --socket "$rootfs/data/qmux_connect_socket"
      --binary-log "$run_dir/qmux-from-client.bin"
      --server-binary-log "$run_dir/qmux-to-client.bin"
      --transcript "$run_dir/qmux-transcript.txt"
    )
    if [[ -n "${QMUX_CLIENT_ID:-}" ]]; then
      qmux_args+=(--client-id "$QMUX_CLIENT_ID")
    fi
    if [[ "${QMUX_REPLY_FIRST:-0}" == 1 ]]; then
      qmux_args+=(--reply-first-sanitized-echo)
    fi
    if [[ "${QMUX_INIT_PROFILE:-0}" == 1 ]]; then
      qmux_args+=(--reply-init-profile)
    fi
    python3 "$tools/qmux_stub.py" "${qmux_args[@]}" &
    qmux_pid=$!
    for _ in $(seq 1 30); do
      [[ -S "$rootfs/data/qmux_connect_socket" ]] && break
      sleep 0.1
    done
    [[ -S "$rootfs/data/qmux_connect_socket" ]] || exit 93
  fi

  sleep 0.2
  ulimit -c 0
  app_path=/data/phnixIot4G
  if [[ "${MQTT_TLS_STUB:-0}" == 1 ]]; then
    app_path=/data/phnixIot4G.tls-lab
  fi
  if [[ "${AUTONOMOUS_DTU_RUNNER:-0}" == 1 ]]; then
    # Start stopped on the QEMU remote-GDB socket. The production DTU runtime
    # hook connects later and remains the sole debugger/OTA orchestrator.
    timeout -k 2 "${run_secs}s" chroot "$rootfs" \
      /usr/bin/qemu-arm-static -g 12345 -L / -strace "$app_path" \
      > "$run_dir/stdout.log" 2> "$run_dir/qemu-strace.log" &
    app_timeout_pid=$!
    wait "$app_timeout_pid"
  elif [[ "${LOCAL_OTA_HANDLER:-0}" == 1 ]]; then
    local_handler_gdb="$tools/gdb_local_ota_handler.gdb"
    if [[ "${LOCAL_OTA_HANDLER_LATE:-0}" == 1 ]]; then
      local_handler_gdb="$tools/gdb_local_ota_handler_late.gdb"
    fi
    timeout -k 2 "${run_secs}s" chroot "$rootfs" \
      /usr/bin/qemu-arm-static -g 12345 -L / -strace "$app_path" \
      > "$run_dir/stdout.log" 2> "$run_dir/qemu-strace.log" &
    app_timeout_pid=$!
    sleep 0.5
    timeout -k 2 "${run_secs}s" gdb-multiarch -q -batch \
      -x "$local_handler_gdb" \
      > "$run_dir/gdb-local-ota-handler.log" 2>&1 || true
    wait "$app_timeout_pid"
  elif [[ "${V33_FULL_TRANSFER:-0}" == 1 ]]; then
    timeout -k 2 "${run_secs}s" chroot "$rootfs" \
      /usr/bin/qemu-arm-static -g 12345 -L / -strace "$app_path" \
      > "$run_dir/stdout.log" 2> "$run_dir/qemu-strace.log" &
    app_timeout_pid=$!
    sleep 0.5
    timeout -k 2 "${run_secs}s" gdb-multiarch -q -batch \
      -x "$tools/gdb_v33_full_transfer.gdb" \
      > "$run_dir/gdb-v33-full-transfer.log" 2>&1 || true
    wait "$app_timeout_pid"
  elif [[ "${V33_DOWNLOAD_PROBE:-0}" == 1 ]]; then
    timeout -k 2 "${run_secs}s" chroot "$rootfs" \
      /usr/bin/qemu-arm-static -g 12345 -L / -strace "$app_path" \
      > "$run_dir/stdout.log" 2> "$run_dir/qemu-strace.log" &
    app_timeout_pid=$!
    sleep 0.5
    timeout -k 2 "${run_secs}s" gdb-multiarch -q -batch \
      -x "$tools/gdb_v33_before_rs485.gdb" \
      > "$run_dir/gdb-v33-before-rs485.log" 2>&1 || true
    wait "$app_timeout_pid"
  elif [[ "${OTA_0033_PARSE_PROBE:-0}" == 1 ]]; then
    timeout -k 2 "${run_secs}s" chroot "$rootfs" \
      /usr/bin/qemu-arm-static -g 12345 -L / -strace "$app_path" \
      > "$run_dir/stdout.log" 2> "$run_dir/qemu-strace.log" &
    app_timeout_pid=$!
    sleep 0.5
    timeout -k 2 "${run_secs}s" gdb-multiarch -q -batch \
      -x "$tools/gdb_ota_0033_parse_probe.gdb" \
      > "$run_dir/gdb-ota-0033-parse-probe.log" 2>&1 || true
    wait "$app_timeout_pid"
  elif [[ "${GDB_SERVICE_PROBE:-0}" == 1 ]]; then
    [[ -f "$tools/gdb_service_probe.gdb" ]] || {
      echo "gdb_service_probe.gdb missing" >&2; exit 94;
    }
    command -v gdb-multiarch >/dev/null || { echo "gdb-multiarch missing" >&2; exit 94; }
    timeout -k 2 "${run_secs}s" chroot "$rootfs" \
      /usr/bin/qemu-arm-static -g 12345 -L / -strace "$app_path" \
      > "$run_dir/stdout.log" 2> "$run_dir/qemu-strace.log" &
    app_timeout_pid=$!
    sleep 0.5
    timeout -k 2 "${run_secs}s" gdb-multiarch -q -batch \
      -x "$tools/gdb_service_probe.gdb" \
      > "$run_dir/gdb-service-probe.log" 2>&1 || true
    wait "$app_timeout_pid"
  elif [[ "${HOST_STRACE:-0}" == 1 ]]; then
    timeout -k 2 "${run_secs}s" strace -f -s 256 -xx \
      -e trace=socket,connect,bind,sendto,recvfrom,sendmsg,recvmsg \
      -o "$run_dir/host-network-strace.log" \
      chroot "$rootfs" /usr/bin/qemu-arm-static -L / -strace "$app_path" \
      > "$run_dir/stdout.log" 2> "$run_dir/qemu-strace.log"
  else
    timeout -k 2 "${run_secs}s" chroot "$rootfs" \
      /usr/bin/qemu-arm-static -L / -strace "$app_path" \
      > "$run_dir/stdout.log" 2> "$run_dir/qemu-strace.log"
  fi
' bash "$ROOTFS" "$TOOLS" "$RUN_DIR" "$RUN_SECS" "$TLS_DIR" "$MQTT_HOST" "$V33_FIXTURE"
rc=$?
set -e
printf '%s\n' "$rc" > "$RUN_DIR/exit-code.txt"

printf 'RUN_DIR=%s\nEXIT_CODE=%s\n' "$RUN_DIR" "$rc"
printf '\n=== AT summary ===\n'
if [[ -f "$RUN_DIR/smd8-transcript.txt" ]]; then
  sed -n '1,24p' "$RUN_DIR/smd8-transcript.txt"
  printf '%s\n' '... final 16 lines ...'
  tail -16 "$RUN_DIR/smd8-transcript.txt"
  printf 'AT command counts:\n'
  sed -n "s/.*APP -> MODEM: '\(.*\)'/\1/p" "$RUN_DIR/smd8-transcript.txt" | sort | uniq -c
fi
if [[ -f "$RUN_DIR/gdb-service-probe.log" ]]; then
  printf '\n=== GDB service-init probe ===\n'
  cat "$RUN_DIR/gdb-service-probe.log"
fi
if [[ -f "$RUN_DIR/gdb-ota-0033-parse-probe.log" ]]; then
  printf '\n=== GDB guarded 0033 parse probe ===\n'
  cat "$RUN_DIR/gdb-ota-0033-parse-probe.log"
fi
if [[ -f "$RUN_DIR/gdb-v33-before-rs485.log" ]]; then
  printf '\n=== GDB V3.3 pre-RS485 guard ===\n'
  cat "$RUN_DIR/gdb-v33-before-rs485.log"
fi
if [[ -f "$RUN_DIR/gdb-v33-full-transfer.log" ]]; then
  printf '\n=== GDB V3.3 full-transfer guard ===\n'
  cat "$RUN_DIR/gdb-v33-full-transfer.log"
fi
if [[ -f "$RUN_DIR/gdb-local-ota-handler.log" ]]; then
  printf '\n=== GDB local OTA handler ===\n'
  cat "$RUN_DIR/gdb-local-ota-handler.log"
fi
printf '\n=== Unknown AT commands ===\n'
sort -u "$RUN_DIR/unknown-at.txt" 2>/dev/null || true
printf '\n=== Device opens ===\n'
grep -aE '/dev/(ttyGS0|smd8|ttyHSL2|diag|smem_log)' "$RUN_DIR/qemu-strace.log" || true
printf '\n=== QMI/QMUX sockets ===\n'
grep -aE 'qmux|qmi|socket\(|connect\(|bind\(' "$RUN_DIR/qemu-strace.log" | tail -160 || true
printf '\n=== Signals and final syscalls ===\n'
grep -aE 'SIGFPE|tgkill|rt_sigaction\(' "$RUN_DIR/qemu-strace.log" | tail -80 || true
tail -80 "$RUN_DIR/qemu-strace.log" || true
if [[ -f "$RUN_DIR/host-network-strace.log" ]]; then
  printf '\n=== Host-decoded network syscalls ===\n'
  grep -aE 'socket\(|connect\(|bind\(|send(to|msg)?\(|recv(from|msg)?\(' \
    "$RUN_DIR/host-network-strace.log" | tail -120 || true
fi
if [[ -f "$RUN_DIR/qmux-transcript.txt" ]]; then
  printf '\n=== QMUX capture-only transcript ===\n'
  cat "$RUN_DIR/qmux-transcript.txt"
fi
if [[ -f "$RUN_DIR/ttyHSL2-transcript.txt" ]]; then
  printf '\n=== RS485 identity-only transcript ===\n'
  cat "$RUN_DIR/ttyHSL2-transcript.txt"
fi
if [[ -f "$RUN_DIR/credential-http-transcript.jsonl" ]]; then
  printf '\n=== Local credential HTTP transcript ===\n'
  cat "$RUN_DIR/credential-http-transcript.jsonl"
fi
if [[ -f "$RUN_DIR/mqtt-tls-transcript.jsonl" ]]; then
  printf '\n=== Local TLS/MQTT transcript (password redacted) ===\n'
  cat "$RUN_DIR/mqtt-tls-transcript.jsonl"
fi
if [[ -f "$RUN_DIR/firmware-http-transcript.jsonl" ]]; then
  printf '\n=== V3.3 loopback HTTP transcript ===\n'
  cat "$RUN_DIR/firmware-http-transcript.jsonl"
fi
