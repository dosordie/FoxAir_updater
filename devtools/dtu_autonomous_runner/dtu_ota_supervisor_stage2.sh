#!/system/bin/sh

# Stage 2 of the autonomous DTU OTA supervisor.
#
# This stage runs the existing phnix_ota_runtime_hook only in its read-only
# `verify` action. It performs NO GDB attach, NO C350 injection, NO firmware
# transfer, NO watchdog pause and NO service control.

umask 077

BASE_DIR=/data/foxair_ota_runner
RUNS_DIR="$BASE_DIR/runs"
LOCK_DIR="$BASE_DIR/active.lock"
LAST_RUN_FILE="$BASE_DIR/last_run_id"

RUN_ID=${1:-}
MODE=${2:-verify}
case "$RUN_ID" in
    ''|*[!A-Za-z0-9._-]*)
        echo "ERROR: invalid run_id" >&2
        exit 2
        ;;
esac

test "$MODE" = verify || {
    echo "ERROR: Stage 2 currently permits verify mode only" >&2
    exit 2
}

RUN_DIR="$RUNS_DIR/$RUN_ID"
PAYLOAD_DIR="$RUN_DIR/payload"
STATUS_FILE="$RUN_DIR/status.json"
STATUS_TMP="$RUN_DIR/status.json.tmp.$$"
RESULT_FILE="$RUN_DIR/result.json"
PID_FILE="$RUN_DIR/runner.pid"
LOG_FILE="$RUN_DIR/runner.log"
HOOK_FILE="$PAYLOAD_DIR/phnix_ota_runtime_hook"
HOOK_STATUS="$RUN_DIR/hook-status.json"
HOOK_LOG="$RUN_DIR/hook.log"
HOOK_PID_FILE="$RUN_DIR/hook.pid"
HOOK_EXPECTED_SHA_FILE="$RUN_DIR/hook.sha256.expected"
HOOK_ACTUAL_SHA_FILE="$RUN_DIR/hook.sha256.actual"

mkdir -p "$PAYLOAD_DIR" || exit 3
printf '%s\n' "$$" > "$PID_FILE" || exit 3

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

runner_ppid() {
    awk '{print $4}' "/proc/$$/stat" 2>/dev/null || printf '0\n'
}

write_status() {
    state=$1
    phase=$2
    terminal=$3
    progress=$4
    reason=$5
    detail=$6
    hook_pid=${7:-0}
    now=$(date +%s)
    ppid=$(runner_ppid)
    reason_json=$(json_escape "$reason")
    detail_json=$(json_escape "$detail")

    printf '{"schema":"foxair-dtu-ota-run-v1","run_id":"%s","state":"%s","phase":"%s","terminal":%s,"progress":%s,"runner_pid":%s,"pid":%s,"ppid":%s,"hook_pid":%s,"updated_at":%s,"time":%s,"transfer_started":false,"original_service_authoritative":false,"recovery":"not-required","reason":"%s","detail":"%s"}\n' \
        "$RUN_ID" "$state" "$phase" "$terminal" "$progress" "$$" "$$" "$ppid" "$hook_pid" "$now" "$now" "$reason_json" "$detail_json" \
        > "$STATUS_TMP" || return 1
    mv "$STATUS_TMP" "$STATUS_FILE"
}

rotate_log_if_needed() {
    test -f "$LOG_FILE" || return 0
    bytes=$(wc -c < "$LOG_FILE" 2>/dev/null || printf '0')
    case "$bytes" in
        ''|*[!0-9]*) bytes=0 ;;
    esac
    if test "$bytes" -gt 262144; then
        tail -c 131072 "$LOG_FILE" > "$LOG_FILE.tmp.$$" 2>/dev/null || return 0
        mv "$LOG_FILE.tmp.$$" "$LOG_FILE" 2>/dev/null || true
    fi
}

log_event() {
    rotate_log_if_needed
    printf '%s run_id=%s pid=%s %s\n' "$(date +%s)" "$RUN_ID" "$$" "$1" >> "$LOG_FILE"
}

release_lock() {
    if test -d "$LOCK_DIR"; then
        owner=$(cat "$LOCK_DIR/run_id" 2>/dev/null || true)
        owner_pid=$(cat "$LOCK_DIR/pid" 2>/dev/null || true)
        if test "$owner" = "$RUN_ID" && test "$owner_pid" = "$$"; then
            rm -f "$LOCK_DIR/run_id" "$LOCK_DIR/pid"
            rmdir "$LOCK_DIR" 2>/dev/null || true
        fi
    fi
}

terminal_exit() {
    state=$1
    phase=$2
    rc=$3
    reason=$4
    detail=$5
    hook_pid=${6:-0}
    write_status "$state" "$phase" true 100 "$reason" "$detail" "$hook_pid" || true
    cp "$STATUS_FILE" "$RESULT_FILE" 2>/dev/null || true
    log_event "terminal state=$state phase=$phase reason=$reason"
    release_lock
    exit "$rc"
}

signal_exit() {
    trap - TERM HUP INT
    terminal_exit failed signal 130 signal_received "Stage-2 supervisor received TERM/HUP/INT." 0
}

trap signal_exit TERM HUP INT

write_status starting lock false 0 "" "Acquiring single-run lock for Stage-2 hook verify." 0 || exit 3

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    owner=$(cat "$LOCK_DIR/run_id" 2>/dev/null || true)
    owner_pid=$(cat "$LOCK_DIR/pid" 2>/dev/null || true)
    terminal_exit failed lock 20 active_run_exists "Another run owns the DTU runner lock: run_id=$owner pid=$owner_pid" 0
fi

printf '%s\n' "$RUN_ID" > "$LOCK_DIR/run_id" || terminal_exit failed lock 21 lock_write_failed "Could not persist lock owner." 0
printf '%s\n' "$$" > "$LOCK_DIR/pid" || terminal_exit failed lock 21 lock_write_failed "Could not persist lock PID." 0
printf '%s\n' "$RUN_ID" > "$LAST_RUN_FILE.tmp.$$" || terminal_exit failed bootstrap 22 last_run_write_failed "Could not write last_run_id." 0
mv "$LAST_RUN_FILE.tmp.$$" "$LAST_RUN_FILE" || terminal_exit failed bootstrap 22 last_run_write_failed "Could not atomically publish last_run_id." 0

log_event "stage2 verify started"
write_status running hook-preflight false 5 "" "Validating staged runtime hook before read-only verify." 0 \
    || terminal_exit failed status 23 status_write_failed "Could not publish Stage-2 preflight status." 0

test -r "$HOOK_FILE" || terminal_exit failed hook-preflight 30 hook_missing "Staged runtime hook is missing." 0
test -r "$HOOK_EXPECTED_SHA_FILE" || terminal_exit failed hook-preflight 31 hook_hash_missing "Expected runtime hook SHA-256 is missing." 0

EXPECTED_HOOK_SHA=$(cat "$HOOK_EXPECTED_SHA_FILE" 2>/dev/null || true)
case "$EXPECTED_HOOK_SHA" in
    [0-9a-fA-F][0-9a-fA-F]*) ;;
    *) terminal_exit failed hook-preflight 32 invalid_hook_hash "Expected runtime hook SHA-256 is invalid." 0 ;;
esac

ACTUAL_HOOK_SHA=$(sha256sum "$HOOK_FILE" 2>/dev/null | awk '{print $1}')
printf '%s\n' "$ACTUAL_HOOK_SHA" > "$HOOK_ACTUAL_SHA_FILE"
test "$ACTUAL_HOOK_SHA" = "$EXPECTED_HOOK_SHA" \
    || terminal_exit failed hook-preflight 33 hook_hash_mismatch "Runtime hook SHA-256 differs after upload." 0

chmod 700 "$HOOK_FILE" 2>/dev/null \
    || terminal_exit failed hook-preflight 34 hook_chmod_failed "Could not make staged runtime hook executable." 0

rm -f "$HOOK_STATUS" "$HOOK_PID_FILE"
write_status running hook-verify-starting false 20 "" "Starting phnix_ota_runtime_hook verify as a local child process." 0 \
    || terminal_exit failed status 23 status_write_failed "Could not publish hook start status." 0

/system/bin/sh "$HOOK_FILE" verify --status "$HOOK_STATUS" >> "$HOOK_LOG" 2>&1 &
HOOK_PID=$!
printf '%s\n' "$HOOK_PID" > "$HOOK_PID_FILE"
log_event "hook child started pid=$HOOK_PID mode=verify"

# If the verify child is still alive, confirm that this PID really belongs to
# the staged runtime hook before treating it as our child identity. The verify
# action can legitimately finish so quickly that /proc/<pid> already vanished.
if test -r "/proc/$HOOK_PID/cmdline"; then
    HOOK_CMD=$(tr '\000' ' ' < "/proc/$HOOK_PID/cmdline" 2>/dev/null || true)
    case "$HOOK_CMD" in
        *phnix_ota_runtime_hook*verify*)
            log_event "hook child identity confirmed pid=$HOOK_PID"
            ;;
        *)
            terminal_exit failed hook-verify 35 hook_identity_mismatch "Live hook PID does not match staged runtime hook verify command." "$HOOK_PID"
            ;;
    esac
fi

write_status running hook-verify false 50 "" "Read-only runtime hook verify is executing locally on the DTU." "$HOOK_PID" \
    || terminal_exit failed status 23 status_write_failed "Could not publish hook verify status." "$HOOK_PID"

HOOK_RC=0
wait "$HOOK_PID" || HOOK_RC=$?
log_event "hook child ended pid=$HOOK_PID rc=$HOOK_RC"

if test "$HOOK_RC" = 0 && grep -q '"phase":"verified"' "$HOOK_STATUS" 2>/dev/null; then
    terminal_exit completed hook-verify-ok 0 "" "Runtime hook verify completed successfully on the DTU; no debugger attach or OTA action was performed." "$HOOK_PID"
fi

FAIL_RC=$HOOK_RC
test "$FAIL_RC" != 0 || FAIL_RC=36
terminal_exit failed hook-verify-failed "$FAIL_RC" hook_verify_failed "Runtime hook verify failed (rc=$HOOK_RC); inspect hook-status.json and hook.log." "$HOOK_PID"
