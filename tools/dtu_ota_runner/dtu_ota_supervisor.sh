#!/system/bin/sh
# Autonomous FoxAir DTU OTA supervisor. Android /system/bin/sh + BusyBox 1.23 compatible.
set -u
umask 077

BASE=/data/foxair_ota_runner
RUNS=$BASE/runs
LOCK=$BASE/active.lock
SCHEMA=foxair-dtu-ota-run-v1
PACKAGE_SCHEMA=foxair-dtu-ota-package-v1
SERVICE=/data/phnixIot4G
HOOK_RUNTIME=/tmp/phnix_ota_hook
EXPECTED_BUILD_FIXED=af4dcae12639bedce833ee5efa5da009777b6319
EXPECTED_SERVICE_FIXED=7C573431F0A67620D473419644A83A4F4DC04B8A91BDE5923C74A63BA1EAEDB7
SHELL_BIN=/system/bin/sh
test -x "$SHELL_BIN" || SHELL_BIN=/bin/sh

ACTION=${1:-}
RUN_ID=${2:-}
case "$RUN_ID" in ''|*[!A-Za-z0-9._-]*) echo "ERROR: invalid run_id" >&2; exit 2 ;; esac

RUN_DIR=$RUNS/$RUN_ID
PAYLOAD=$RUN_DIR/payload
PACKAGE=$RUN_DIR/package.json
PACKAGE_SHA_FILE=$RUN_DIR/package.sha256
STATUS=$RUN_DIR/status.json
RESULT=$RUN_DIR/result.json
LOG=$RUN_DIR/runner.log
PID_FILE=$RUN_DIR/runner.pid
HOOK=$PAYLOAD/runtime_hook
HOOK_STATUS=$RUN_DIR/hook-status.json
HOOK_LOG=$RUN_DIR/hook.log
COMMAND=$PAYLOAD/ota-command.json
FIRMWARE=$PAYLOAD/firmware.bin
ABORT=$RUN_DIR/abort.request

json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/[[:cntrl:]]/ /g'; }
json_string() { sed -n "s/.*\"$1\":\"\([^\"]*\)\".*/\1/p" "$PACKAGE" | head -n 1; }
json_number() { sed -n "s/.*\"$1\":\([0-9][0-9]*\).*/\1/p" "$PACKAGE" | head -n 1; }
json_bool() { sed -n "s/.*\"$1\":\(true\|false\).*/\1/p" "$PACKAGE" | head -n 1; }
status_string() { sed -n "s/.*\"$1\":\"\([^\"]*\)\".*/\1/p" "$STATUS" 2>/dev/null | head -n 1; }
status_bool() { sed -n "s/.*\"$1\":\(true\|false\).*/\1/p" "$STATUS" 2>/dev/null | head -n 1; }
hook_string() { sed -n "s/.*\"$1\":\"\([^\"]*\)\".*/\1/p" "$HOOK_STATUS" 2>/dev/null | head -n 1; }
hook_bool() { sed -n "s/.*\"$1\":\(true\|false\).*/\1/p" "$HOOK_STATUS" 2>/dev/null | head -n 1; }
hook_number() { sed -n "s/.*\"$1\":\([0-9][0-9]*\).*/\1/p" "$HOOK_STATUS" 2>/dev/null | head -n 1; }

rotate_log() {
    test -f "$LOG" || return 0
    size=$(wc -c < "$LOG" 2>/dev/null || echo 0)
    case "$size" in ''|*[!0-9]*) size=0 ;; esac
    if test "$size" -gt 524288; then
        test -f "$LOG.2" && mv "$LOG.2" "$LOG.3" 2>/dev/null || true
        test -f "$LOG.1" && mv "$LOG.1" "$LOG.2" 2>/dev/null || true
        mv "$LOG" "$LOG.1" 2>/dev/null || true
    fi
}
log_event() { rotate_log; printf '%s run_id=%s pid=%s %s\n' "$(date +%s)" "$RUN_ID" "$$" "$1" >> "$LOG"; }

TRANSFER_STARTED=false
ORIGINAL_AUTH=false
ABORT_ALLOWED=true
OFFSET=0
LENGTH=0
PROGRESS=0
HOOK_PID=0
SERVICE_PID=0
STARTED_AT=0
PACKAGE_SHA=
FIRMWARE_SHA=
RECOVERY=not-required
BOARD_STEP=0
C36E_STATUS=0
C36E_SEEN=false
C350_SENT=false
C357_SENT=false
C5A8_SENT=false
STATE_RESTORED=false
RESULT_TYPE=

load_status_state() {
    test -r "$STATUS" || return 0
    v=$(status_bool transfer_started); test -n "$v" && TRANSFER_STARTED=$v
    v=$(status_bool original_service_authoritative); test -n "$v" && ORIGINAL_AUTH=$v
    v=$(status_bool abort_allowed); test -n "$v" && ABORT_ALLOWED=$v
    v=$(status_string recovery); test -n "$v" && RECOVERY=$v
    v=$(status_string package_sha256); test -n "$v" && PACKAGE_SHA=$v
    v=$(status_string firmware_sha256); test -n "$v" && FIRMWARE_SHA=$v
    v=$(status_bool c36e_seen); test -n "$v" && C36E_SEEN=$v
    v=$(status_bool c350_sent); test -n "$v" && C350_SENT=$v
    v=$(status_bool c357_sent); test -n "$v" && C357_SENT=$v
    v=$(status_bool c5a8_sent); test -n "$v" && C5A8_SENT=$v
    v=$(status_bool state_restored); test -n "$v" && STATE_RESTORED=$v
    v=$(sed -n 's/.*"c36e_status":\([0-9][0-9]*\).*/\1/p' "$STATUS" 2>/dev/null | head -n 1)
    test -n "$v" && C36E_STATUS=$v
}

write_status() {
    state=$1 phase=$2 terminal=$3 reason=$4 detail=$5
    now=$(date +%s)
    test "$STARTED_AT" != 0 || STARTED_AT=$now
    tmp=$STATUS.tmp.$$
    case "$SERVICE_PID" in ''|*[!0-9]*) SERVICE_PID=0 ;; esac
    printf '{"schema":"%s","run_id":"%s","state":"%s","phase":"%s","terminal":%s,"progress":%s,"offset":%s,"length":%s,"transfer_started":%s,"original_service_authoritative":%s,"abort_allowed":%s,"recovery":"%s","reason":"%s","detail":"%s","result_type":"%s","runner_pid":%s,"hook_pid":%s,"service_pid":%s,"started_at":%s,"last_activity_at":%s,"updated_at":%s,"package_sha256":"%s","firmware_sha256":"%s","board_ota_step":%s,"c36e_seen":%s,"c36e_status":%s,"c350_sent":%s,"c357_sent":%s,"c5a8_sent":%s,"state_restored":%s}\n' \
        "$SCHEMA" "$RUN_ID" "$state" "$phase" "$terminal" "$PROGRESS" "$OFFSET" "$LENGTH" \
        "$TRANSFER_STARTED" "$ORIGINAL_AUTH" "$ABORT_ALLOWED" "$RECOVERY" \
        "$(json_escape "$reason")" "$(json_escape "$detail")" "$RESULT_TYPE" "$$" "$HOOK_PID" "$SERVICE_PID" \
        "$STARTED_AT" "$now" "$now" "$PACKAGE_SHA" "$FIRMWARE_SHA" "$BOARD_STEP" "$C36E_SEEN" "$C36E_STATUS" \
        "$C350_SENT" "$C357_SENT" "$C5A8_SENT" "$STATE_RESTORED" > "$tmp" || return 1
    mv "$tmp" "$STATUS"
}

terminal_result() {
    RESULT_TYPE=$1 state=$2 phase=$3 rc=$4 reason=$5 detail=$6
    write_status "$state" "$phase" true "$reason" "$detail" || true
    cp "$STATUS" "$RESULT.tmp.$$" 2>/dev/null && mv "$RESULT.tmp.$$" "$RESULT" 2>/dev/null || true
    log_event "terminal result=$RESULT_TYPE phase=$phase reason=$reason"
    release_lock
    stop_http
    exit "$rc"
}

runner_identity() {
    pid=$1 expected_run=$2
    case "$pid" in ''|*[!0-9]*) return 1 ;; esac
    test -r "/proc/$pid/cmdline" || return 1
    cmd=$(tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
    case "$cmd" in *dtu_ota_supervisor.sh*" run $expected_run"*) return 0 ;; *) return 1 ;; esac
}

release_lock() {
    test -d "$LOCK" || return 0
    owner=$(cat "$LOCK/run_id" 2>/dev/null || true)
    owner_pid=$(cat "$LOCK/pid" 2>/dev/null || true)
    if test "$owner" = "$RUN_ID" && test "$owner_pid" = "$$"; then
        rm -f "$LOCK/run_id" "$LOCK/pid" "$LOCK/started_at"
        rmdir "$LOCK" 2>/dev/null || true
    fi
}

acquire_lock() {
    if ! mkdir "$LOCK" 2>/dev/null; then
        owner=$(cat "$LOCK/run_id" 2>/dev/null || true)
        owner_pid=$(cat "$LOCK/pid" 2>/dev/null || true)
        if runner_identity "$owner_pid" "$owner"; then
            terminal_result failed failed lock 20 active_run_exists "Active run $owner owns PID $owner_pid."
        fi
        terminal_result orphaned failed stale-lock 21 stale_lock "Lock owner cannot be proven; refusing to remove it automatically."
    fi
    printf '%s\n' "$RUN_ID" > "$LOCK/run_id" || return 1
    printf '%s\n' "$$" > "$LOCK/pid" || return 1
    date +%s > "$LOCK/started_at" || return 1
}

upper_hash() { "$1" "$2" 2>/dev/null | awk '{print toupper($1)}'; }
valid_hash() { case "$1" in *[!0-9A-F]*|'') return 1 ;; esac; test "${#1}" = "$2"; }

service_pids() {
    found=
    for pid in $(pidof phnixIot4G 2>/dev/null || true); do
        case "$pid" in ''|*[!0-9]*) continue ;; esac
        cmd=$(tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
        case "$cmd" in *phnixIot4G*) found="$found $pid" ;; esac
    done
    if test -z "$found" && test -f /data/phnixIot4G.tls-lab; then
        for proc in /proc/[0-9]*; do
            exe=$(readlink "$proc/exe" 2>/dev/null || true)
            cmd=$(tr '\000' ' ' < "$proc/cmdline" 2>/dev/null || true)
            case "$exe:$cmd" in *qemu-arm-static:*phnixIot4G.tls-lab*) found="$found $(basename "$proc")" ;; esac
        done
    fi
    printf '%s\n' "$found" | awk '{$1=$1; print}'
}

single_service_pid() {
    pids=$(service_pids)
    count=$(printf '%s\n' "$pids" | awk '{print NF}')
    test "$count" = 1 || return 1
    printf '%s\n' "$pids"
}

load_package() {
    test -r "$PACKAGE" || return 30
    test -r "$PACKAGE_SHA_FILE" || return 31
    expected=$(tr -d '\r\n ' < "$PACKAGE_SHA_FILE" | tr 'a-f' 'A-F')
    actual=$(sha256sum "$PACKAGE" 2>/dev/null | awk '{print toupper($1)}')
    valid_hash "$expected" 64 || return 32
    test "$actual" = "$expected" || return 33
    PACKAGE_SHA=$actual
    test "$(json_string schema)" = "$PACKAGE_SCHEMA" || return 34
    test "$(json_string run_id)" = "$RUN_ID" || return 35
    test "$(json_string firmware_file)" = firmware.bin || return 36
    test "$(json_string hook_file)" = runtime_hook || return 37
    test "$(json_string runner_file)" = dtu_ota_supervisor.sh || return 38
    test "$(json_string target_ssid)" = 0063 || return 39
    test "$(json_string image_base)" = 0x08050000 || return 40
    test "$(json_string publish_allowlist)" = 0023,0053,0083 || return 41
    MODE=$(json_string mode); case "$MODE" in full|same-version) ;; *) return 42 ;; esac
    RESTART_SERVICE=$(json_bool restart_service_before_update); case "$RESTART_SERVICE" in true|false) ;; *) return 43 ;; esac
    ISOLATE_MQTT=$(json_bool isolate_mqtt); case "$ISOLATE_MQTT" in true|false) ;; *) return 44 ;; esac
    FIRMWARE_SIZE=$(json_number firmware_size); case "$FIRMWARE_SIZE" in ''|*[!0-9]*) return 45 ;; esac
    MARGIN=$(json_number minimum_free_margin_bytes); case "$MARGIN" in ''|*[!0-9]*) return 46 ;; esac
    FIRMWARE_MD5=$(json_string firmware_md5); FIRMWARE_SHA=$(json_string firmware_sha256)
    HOOK_SHA=$(json_string hook_sha256); COMMAND_SHA=$(json_string command_sha256); RUNNER_SHA=$(json_string runner_sha256)
    EXPECTED_SERVICE=$(json_string expected_service_sha256); EXPECTED_BUILD=$(json_string expected_service_build_id)
    valid_hash "$FIRMWARE_MD5" 32 || return 47
    valid_hash "$FIRMWARE_SHA" 64 || return 48
    valid_hash "$HOOK_SHA" 64 || return 49
    valid_hash "$COMMAND_SHA" 64 || return 50
    valid_hash "$RUNNER_SHA" 64 || return 51
    valid_hash "$EXPECTED_SERVICE" 64 || return 52
    test "$EXPECTED_SERVICE" = "$EXPECTED_SERVICE_FIXED" || return 53
    test "$EXPECTED_BUILD" = "$EXPECTED_BUILD_FIXED" || return 54
    test -r "$FIRMWARE" && test -r "$HOOK" && test -r "$COMMAND" || return 55
    test "$(wc -c < "$FIRMWARE" 2>/dev/null)" = "$FIRMWARE_SIZE" || return 56
    test "$(md5sum "$FIRMWARE" 2>/dev/null | awk '{print toupper($1)}')" = "$FIRMWARE_MD5" || return 57
    test "$(sha256sum "$FIRMWARE" 2>/dev/null | awk '{print toupper($1)}')" = "$FIRMWARE_SHA" || return 58
    test "$(sha256sum "$HOOK" 2>/dev/null | awk '{print toupper($1)}')" = "$HOOK_SHA" || return 59
    test "$(sha256sum "$COMMAND" 2>/dev/null | awk '{print toupper($1)}')" = "$COMMAND_SHA" || return 60
    test "$(sha256sum "$0" 2>/dev/null | awk '{print toupper($1)}')" = "$RUNNER_SHA" || return 61
    grep -q "$EXPECTED_BUILD" "$HOOK" 2>/dev/null || return 62
    test -x "$SERVICE" || return 63
    test "$(sha256sum "$SERVICE" 2>/dev/null | awk '{print toupper($1)}')" = "$EXPECTED_SERVICE" || return 64
    SERVICE_PID=$(single_service_pid) || return 65
    case "$SERVICE_PID" in ''|*[!0-9]*) return 65 ;; esac
    test "$(awk '/^TracerPid:/ {print $2}' /proc/$SERVICE_PID/status 2>/dev/null)" = 0 || return 66
    wd_count=$(ps | awk '$4 == "{helloworld}" {n++} END {print n+0}')
    test "$wd_count" -ge 1 || { test -f /data/phnixIot4G.tls-lab && wd_count=2; }
    test "$wd_count" -ge 1 || return 67
    test -x /usr/bin/gdb || return 68
    test -x /usr/bin/gdbserver || test -f /data/phnixIot4G.tls-lab || return 68
    busybox --list 2>/dev/null | grep -qx httpd || return 69
    test -r /data/phnixIot_device_OTA_INFO && test -w /data/phnixIot_device_OTA_INFO || return 70
    test -r /data/phnixIot_device_statisic && test -w /data/phnixIot_device_statisic || return 71
    for marker in run.active transfer-started original-service-owns; do test ! -e "$HOOK_RUNTIME/$marker" || return 72; done
    free_k=$(df -k "$RUN_DIR" 2>/dev/null | awk 'NR==2 {print $4}')
    case "$free_k" in ''|*[!0-9]*) return 73 ;; esac
    required=$((FIRMWARE_SIZE * 2 + MARGIN))
    test $((free_k * 1024)) -ge "$required" || return 74
    return 0
}

preflight_action() {
    mkdir -p "$RUN_DIR" "$PAYLOAD" "$RUN_DIR/state" || exit 3
    load_package; rc=$?
    if test "$rc" != 0; then
        RECOVERY=not-required RESULT_TYPE=failed
        write_status failed package-preflight true package_validation_failed "DTU package validation failed with code $rc before any service or OTA action."
        cp "$STATUS" "$RESULT" 2>/dev/null || true
        exit "$rc"
    fi
    printf '%s\n' "$RUN_ID" > "$BASE/last_run_id.tmp.$$" && mv "$BASE/last_run_id.tmp.$$" "$BASE/last_run_id"
    chmod 700 "$HOOK" "$0" 2>/dev/null || exit 75
    write_status prepared dry-run-complete false "" "Package, hashes, storage, service build and prerequisites verified locally on the DTU; no GDB attach or OTA action occurred."
}

restart_service() {
    old_pids=$(service_pids)
    test -n "$old_pids" || return 1
    for old in $old_pids; do
        cmd=$(tr '\000' ' ' < "/proc/$old/cmdline" 2>/dev/null || true)
        case "$cmd" in *phnixIot4G*) ;; *) return 1 ;; esac
    done
    for old in $old_pids; do kill -TERM "$old" 2>/dev/null || return 1; done
    count=0
    stable_pid=
    stable_count=0
    while test "$count" -lt 60; do
        sleep 1
        current=$(service_pids)
        current_count=$(printf '%s\n' "$current" | awk '{print NF}')
        if test "$current_count" -gt 1; then return 2; fi
        if test "$current_count" = 1; then
            new=$current
            is_old=false
            for old in $old_pids; do test "$new" = "$old" && is_old=true; done
            if test "$is_old" = false; then
                if test "$stable_pid" = "$new"; then stable_count=$((stable_count + 1)); else stable_pid=$new; stable_count=1; fi
                if test "$stable_count" -ge 10; then
                    test "$(awk '/^TracerPid:/ {print $2}' /proc/$new/status 2>/dev/null)" = 0 || return 3
                    SERVICE_PID=$new
                    return 0
                fi
            fi
        else
            stable_pid=
            stable_count=0
        fi
        count=$((count + 1))
    done
    return 1
}

start_http() {
    # A safely finished legacy host-driven run can leave only its localhost
    # staging server behind. No hook marker is present at this point (checked
    # by load_package), so remove only that exact, non-authoritative process.
    for proc in /proc/[0-9]*; do
        cmd=$(tr '\000' ' ' < "$proc/cmdline" 2>/dev/null || true)
        case "$cmd" in *"busybox httpd -p 127.0.0.1:8081 -h /data/phnix_local_ota"*)
            kill -TERM "$(basename "$proc")" 2>/dev/null || true ;;
        esac
    done
    busybox httpd -p 127.0.0.1:8081 -h "$PAYLOAD" || return 1
    curl -fsS http://127.0.0.1:8081/firmware.bin 2>/dev/null | md5sum | awk '{print toupper($1)}' > "$RUN_DIR/served.md5"
    test "$(cat "$RUN_DIR/served.md5" 2>/dev/null)" = "$FIRMWARE_MD5"
}

stop_http() {
    for proc in /proc/[0-9]*; do
        cmd=$(tr '\000' ' ' < "$proc/cmdline" 2>/dev/null || true)
        case "$cmd" in *"busybox httpd -p 127.0.0.1:8081"*"-h $PAYLOAD"*)
            kill -TERM "$(basename "$proc")" 2>/dev/null || true ;;
        esac
    done
}

refresh_progress() {
    if test -r /data/phnixIot_device_OTA_INFO && test "$(wc -c < /data/phnixIot_device_OTA_INFO 2>/dev/null)" = 220; then
        next_offset=$(od -An -tu4 -j212 -N4 /data/phnixIot_device_OTA_INFO 2>/dev/null | tr -d ' ')
        next_length=$(od -An -tu4 -j216 -N4 /data/phnixIot_device_OTA_INFO 2>/dev/null | tr -d ' ')
        case "$next_offset" in ''|*[!0-9]*) next_offset=0 ;; esac
        case "$next_length" in ''|*[!0-9]*) next_length=0 ;; esac
        # The original service clears offset/length during terminal cleanup.
        # Preserve the last confirmed transfer counters in the durable result
        # instead of turning a completed N/N transfer back into 0/0.
        if test "$next_length" -gt 0 && { test "$LENGTH" = 0 || test "$next_length" = "$LENGTH"; } && test "$next_offset" -ge "$OFFSET"; then
            OFFSET=$next_offset
            LENGTH=$next_length
            PROGRESS=$((OFFSET * 100 / LENGTH))
            test "$PROGRESS" -le 100 || PROGRESS=100
        fi
    fi
}

run_action() {
    mkdir -p "$RUN_DIR/state" || exit 3
    load_status_state
    load_package; rc=$?
    test "$rc" = 0 || terminal_result failed failed package-preflight "$rc" package_validation_failed "Package changed or became invalid before start (code $rc)."
    acquire_lock || terminal_result failed failed lock 22 lock_write_failed "Could not persist lock ownership."
    printf '%s\n' "$$" > "$PID_FILE"
    printf '%s\n' "$RUN_ID" > "$BASE/last_run_id.tmp.$$" && mv "$BASE/last_run_id.tmp.$$" "$BASE/last_run_id"
    write_status running local-preparation false "" "DTU supervisor owns the prepared run."
    cp -p /data/phnixIot_device_OTA_INFO "$RUN_DIR/state/OTA_INFO" || terminal_result failed failed backup 80 backup_failed "Could not persist OTA_INFO backup."
    cp -p /data/phnixIot_device_statisic "$RUN_DIR/state/statisic" || terminal_result failed failed backup 80 backup_failed "Could not persist statistics backup."
    sha256sum "$RUN_DIR/state/OTA_INFO" "$RUN_DIR/state/statisic" > "$RUN_DIR/state/SHA256SUMS"
    if test "$RESTART_SERVICE" = true; then
        write_status running service-restart-wait false "" "Controlled service restart requested; waiting for exactly one new stable, untraced process."
        restart_service; restart_rc=$?
        test "$restart_rc" = 0 || terminal_result failed failed service-restart 81 service_restart_failed "Original service restart was not uniquely stable (code $restart_rc); no OTA action was started."
        load_package; rc=$?
        test "$rc" = 0 || terminal_result failed failed post-restart-preflight "$rc" post_restart_preflight_failed "Prerequisites failed after local service restart (code $rc)."
        write_status running service-restart-verified false "" "Exactly one new stable original-service PID was verified after restart."
    fi
    start_http || terminal_result failed failed staging 82 local_http_failed "Local firmware HTTP staging verification failed."
    rm -f "$HOOK_STATUS" "$ABORT"
    args="run --build-id $EXPECTED_BUILD --command $COMMAND --status $HOOK_STATUS --allow-publish 0023,0053,0083"
    test "$ISOLATE_MQTT" = true && args="$args --isolate-mqtt"
    "$SHELL_BIN" "$HOOK" $args >> "$HOOK_LOG" 2>&1 &
    HOOK_PID=$!
    printf '%s\n' "$HOOK_PID" > "$RUN_DIR/hook.pid"
    write_status running hook-started false "" "Runtime hook is a local child of the autonomous DTU supervisor."
    post_abort_logged=0
    while :; do
        refresh_progress
        test -e "$HOOK_RUNTIME/original-service-owns" && ORIGINAL_AUTH=true ABORT_ALLOWED=false
        if test -e "$HOOK_RUNTIME/transfer-started"; then
            TRANSFER_STARTED=true ORIGINAL_AUTH=true ABORT_ALLOWED=false C5A8_SENT=true
        fi
        phase=$(hook_string phase)
        terminal=$(hook_bool terminal)
        test -n "$phase" || phase=hook-starting
        sticky=$(hook_bool c350_sent); test "$sticky" = true && C350_SENT=true
        sticky=$(hook_bool c357_sent); test "$sticky" = true && C357_SENT=true
        sticky=$(hook_bool c5a8_sent); test "$sticky" = true && C5A8_SENT=true
        seen=$(hook_bool c36e_seen)
        if test "$seen" = true; then
            C36E_SEEN=true
            value=$(hook_number c36e_status); test -n "$value" && C36E_STATUS=$value
        fi
        case "$phase" in
            c350|c350-sent) C350_SENT=true ;;
            same-version|c350-same-version) C350_SENT=true; C36E_SEEN=true; C36E_STATUS=0 ;;
            accepted) C350_SENT=true; C36E_SEEN=true; C36E_STATUS=1; ORIGINAL_AUTH=true; ABORT_ALLOWED=false ;;
            c357) C357_SENT=true ;;
            c5a8) C5A8_SENT=true; TRANSFER_STARTED=true; ORIGINAL_AUTH=true; ABORT_ALLOWED=false ;;
            success-report|failure-report) ORIGINAL_AUTH=true; ABORT_ALLOWED=false ;;
        esac
        step=$(hook_number board_ota_step); test -n "$step" && BOARD_STEP=$step
        restored=$(hook_bool state_restored); test -n "$restored" && STATE_RESTORED=$restored
        if test -f "$ABORT"; then
            if test "$ABORT_ALLOWED" = true; then
                log_event "abort request accepted before point-of-no-return"
                if kill -0 "$HOOK_PID" 2>/dev/null; then "$SHELL_BIN" "$HOOK" restore-original --status "$RUN_DIR/abort-status.json" >> "$HOOK_LOG" 2>&1 || true; fi
                RECOVERY=completed STATE_RESTORED=true
                terminal_result aborted-before-transfer aborted aborted-before-transfer 130 abort_requested "Abort request completed using the validated pre-transfer recovery path."
            elif test "$post_abort_logged" = 0; then
                post_abort_logged=1
                log_event "abort request refused after authority handoff; observation continues"
            fi
        fi
        if test "$terminal" = true; then
            case "$phase" in
                same-version|c350-same-version)
                    C350_SENT=true C36E_SEEN=true C36E_STATUS=0 STATE_RESTORED=true RECOVERY=completed PROGRESS=0
                    terminal_result same-version completed same-version 0 "" "Mainboard rejected the equal version safely; no firmware blocks were transferred."
                    ;;
                success)
                    test "$BOARD_STEP" = 12 || terminal_result recovery-required failed invalid-success-boundary 90 missing_step12 "Hook claimed success without board OTA step 12."
                    PROGRESS=100
                    terminal_result success completed success 0 "" "Mainboard success report and final step 12 were both confirmed."
                    ;;
                failed)
                    RECOVERY=required
                    terminal_result failed failed failed 91 board_update_failed "Mainboard failure report reached the validated terminal boundary."
                    ;;
                precondition-rejected|parser-rejected)
                    RECOVERY=completed STATE_RESTORED=true
                    terminal_result recovery-completed failed "$phase" 92 "$phase" "OTA was rejected before authority handoff and persistent state was restored."
                    ;;
                *)
                    RECOVERY=required
                    terminal_result recovery-required failed "$phase" 93 unexpected_terminal_hook_state "Unexpected terminal hook phase."
                    ;;
            esac
        fi
        if ! kill -0 "$HOOK_PID" 2>/dev/null; then
            wait "$HOOK_PID" 2>/dev/null; hook_rc=$?
            if test "$ORIGINAL_AUTH" = true; then
                RECOVERY=required ABORT_ALLOWED=false
                terminal_result recovery-required failed original-service-active-unmonitored "$hook_rc" hook_monitor_lost "Hook ended after authority handoff; the original service was not stopped or restored."
            fi
            "$SHELL_BIN" "$HOOK" restore-original --status "$RUN_DIR/recovery-status.json" >> "$HOOK_LOG" 2>&1 || true
            RECOVERY=completed STATE_RESTORED=true
            terminal_result recovery-completed failed hook-ended-before-authority "$hook_rc" hook_ended "Hook ended before authority handoff; validated pre-transfer recovery was requested."
        fi
        detail="Autonomous DTU OTA is running."
        test -f "$ABORT" && test "$ABORT_ALLOWED" = false && detail="Abort request recorded but refused after point-of-no-return; original service continues."
        write_status running "$phase" false "" "$detail" || true
        sleep 2
    done
}

classify_action() {
    test -r "$STATUS" || exit 0
    test "$(status_bool terminal)" = true && exit 0
    # A completed preflight is intentionally non-terminal because start may
    # follow later.  The short-lived preflight PID is not an orphaned OTA.
    test "$(status_string state)" = prepared && exit 0
    pid=$(sed -n 's/.*"runner_pid":\([0-9][0-9]*\).*/\1/p' "$STATUS" | head -n 1)
    runner_identity "$pid" "$RUN_ID" && exit 0
    load_status_state
    RECOVERY=required ABORT_ALLOWED=false RESULT_TYPE=reboot-detected
    if test "$TRANSFER_STARTED" = true || test "$ORIGINAL_AUTH" = true; then
        write_status failed reboot-detected true reboot_detected "Runner disappeared after authority handoff; no automatic resume or generic restore is attempted."
    else
        RESULT_TYPE=orphaned ABORT_ALLOWED=true
        write_status failed orphaned-run true orphaned_run "Runner disappeared before transfer; state is classified but not automatically resumed."
    fi
    cp "$STATUS" "$RESULT.tmp.$$" 2>/dev/null && mv "$RESULT.tmp.$$" "$RESULT" 2>/dev/null || true
    # A dead owner must not block every future run.  Retain the complete run
    # directory/result for diagnosis, but clear only the exactly matched,
    # proven-dead lock.  No OTA state is restored and no run is resumed.
    if test -d "$LOCK" && test "$(cat "$LOCK/run_id" 2>/dev/null)" = "$RUN_ID"; then
        lock_pid=$(cat "$LOCK/pid" 2>/dev/null || true)
        if ! runner_identity "$lock_pid" "$RUN_ID"; then
            rm -f "$LOCK/run_id" "$LOCK/pid" "$LOCK/started_at"
            rmdir "$LOCK" 2>/dev/null || true
        fi
    fi
}

ack_action() {
    test "$(status_bool terminal)" = true || { echo "ERROR: run is not terminal" >&2; exit 100; }
    touch "$RUN_DIR/acknowledged"
}

cleanup_action() {
    test "$(status_bool terminal)" = true || { echo "ERROR: run is not terminal" >&2; exit 100; }
    test -f "$RUN_DIR/acknowledged" || { echo "ERROR: run is not acknowledged" >&2; exit 101; }
    type=$(status_string result_type)
    case "$type" in success|same-version|recovery-completed|aborted-before-transfer) ;; *) echo "ERROR: diagnostics retained for result $type" >&2; exit 102 ;; esac
    pid=$(cat "$PID_FILE" 2>/dev/null || true)
    runner_identity "$pid" "$RUN_ID" && { echo "ERROR: runner still active" >&2; exit 103; }
    if test -d "$LOCK" && test "$(cat "$LOCK/run_id" 2>/dev/null)" = "$RUN_ID"; then
        lock_pid=$(cat "$LOCK/pid" 2>/dev/null || true)
        runner_identity "$lock_pid" "$RUN_ID" && { echo "ERROR: live lock owner" >&2; exit 104; }
        rm -f "$LOCK/run_id" "$LOCK/pid" "$LOCK/started_at"; rmdir "$LOCK" 2>/dev/null || true
    fi
    rm -rf "$RUN_DIR"
}

case "$ACTION" in
    preflight) preflight_action ;;
    run) run_action ;;
    classify) classify_action ;;
    ack) ack_action ;;
    cleanup) cleanup_action ;;
    *) echo "usage: $0 preflight|run|classify|ack|cleanup RUN_ID" >&2; exit 2 ;;
esac
