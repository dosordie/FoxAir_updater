#!/system/bin/sh

# Stage 2 of the autonomous DTU OTA supervisor.
#
# This stage runs the existing phnix_ota_runtime_hook either in its read-only
# `verify` action or in the explicitly selected `attach-test` action.
#
# verify:
#   NO GDB attach, NO C350 injection, NO firmware transfer, NO watchdog pause
#   and NO service control.
#
# attach-test:
#   performs the hook's existing read-only GDB attach/detach test. It pauses
#   the service watchdogs while attached and reads a few fixed addresses, but
#   performs NO parser injection, NO C350 and NO firmware transfer.

umask 077

BASE_DIR=/data/foxair_ota_runner
RUNS_DIR="$BASE_DIR/runs"
LOCK_DIR="$BASE_DIR/active.lock"
LAST_RUN_FILE="$BASE_DIR/last_run_id"
HOOK_RUNTIME_DIR=/tmp/phnix_ota_hook

RUN_ID=${1:-}
MODE=${2:-verify}
case "$RUN_ID" in
    ''|*[!A-Za-z0-9._-]*)
        echo "ERROR: invalid run_id" >&2
        exit 2
        ;;
esac

case "$MODE" in
    verify|attach-test) ;;
    *)
        echo "ERROR: Stage 2 permits verify or attach-test mode only" >&2
        exit 2
        ;;
esac

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

write_status starting lock false 0 "" "Acquiring single-run lock for Stage-2 hook $MODE." 0 || exit 3

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    owner=$(cat "$LOCK_DIR/run_id" 2>/dev/null || true)
    owner_pid=$(cat "$LOCK_DIR/pid" 2>/dev/null || true)
    terminal_exit failed lock 20 active_run_exists "Another run owns the DTU runner lock: run_id=$owner pid=$owner_pid" 0
fi

printf '%s\n' "$RUN_ID" > "$LOCK_DIR/run_id" || terminal_exit failed lock 21 lock_write_failed "Could not persist lock owner." 0
printf '%s\n' "$$" > "$LOCK_DIR/pid" || terminal_exit failed lock 21 lock_write_failed "Could not persist lock PID." 0
printf '%s\n' "$RUN_ID" > "$LAST_RUN_FILE.tmp.$$" || terminal_exit failed bootstrap 22 last_run_write_failed "Could not write last_run_id." 0
mv "$LAST_RUN_FILE.tmp.$$" "$LAST_RUN_FILE" || terminal_exit failed bootstrap 22 last_run_write_failed "Could not atomically publish last_run_id." 0

log_event "stage2 mode=$MODE started"
write_status running hook-preflight false 5 "" "Validating staged runtime hook before $MODE." 0 \
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

# The read-only attach-test uses the hook's global /tmp runtime directory.
# Never let this diagnostic test enter an existing OTA/guarded state. A stale
# SAFE_TO_CLEAN marker by itself is harmless, but any active/transfer/authority
# marker is treated as a hard conflict and the test fails closed before GDB.
if test "$MODE" = attach-test; then
    for marker in run.active transfer-started injection-started original-service-owns; do
        if test -e "$HOOK_RUNTIME_DIR/$marker"; then
            terminal_exit failed hook-preflight 37 existing_hook_runtime_state \
                "Refusing attach-test because $HOOK_RUNTIME_DIR/$marker already exists." 0
        fi
    done
fi

rm -f "$HOOK_STATUS" "$HOOK_PID_FILE"

case "$MODE" in
    verify)
        START_PHASE=hook-verify-starting
        RUN_PHASE=hook-verify
        OK_HOOK_PHASE=verified
        OK_PHASE=hook-verify-ok
        START_DETAIL="Starting phnix_ota_runtime_hook verify as a local child process."
        RUN_DETAIL="Read-only runtime hook verify is executing locally on the DTU."
        OK_DETAIL="Runtime hook verify completed successfully on the DTU; no debugger attach or OTA action was performed."
        FAIL_PHASE=hook-verify-failed
        FAIL_REASON=hook_verify_failed
        FAIL_DETAIL="Runtime hook verify failed"
        ;;
    attach-test)
        START_PHASE=hook-attach-test-starting
        RUN_PHASE=hook-attach-test
        OK_HOOK_PHASE=attach-test-ok
        OK_PHASE=hook-attach-test-ok
        START_DETAIL="Starting the runtime hook read-only GDB attach/detach test as a local child process."
        RUN_DETAIL="Runtime hook attach-test is executing locally on the DTU; no parser injection or OTA command is permitted."
        OK_DETAIL="Runtime hook read-only attach/detach test completed successfully; no C350 or firmware transfer was performed."
        FAIL_PHASE=hook-attach-test-failed
        FAIL_REASON=hook_attach_test_failed
        FAIL_DETAIL="Runtime hook attach-test failed"
        ;;
esac

write_status running "$START_PHASE" false 20 "" "$START_DETAIL" 0 \
    || terminal_exit failed status 23 status_write_failed "Could not publish hook start status." 0

/system/bin/sh "$HOOK_FILE" "$MODE" --status "$HOOK_STATUS" >> "$HOOK_LOG" 2>&1 &
HOOK_PID=$!
printf '%s\n' "$HOOK_PID" > "$HOOK_PID_FILE"
log_event "hook child started pid=$HOOK_PID mode=$MODE"

# If the child is still alive, confirm that this PID really belongs to the
# staged runtime hook and the requested mode. Either action can finish quickly
# enough that /proc/<pid> already vanished before this check.
if test -r "/proc/$HOOK_PID/cmdline"; then
    HOOK_CMD=$(tr '\000' ' ' < "/proc/$HOOK_PID/cmdline" 2>/dev/null || true)
    case "$MODE:$HOOK_CMD" in
        verify:*phnix_ota_runtime_hook*verify*|attach-test:*phnix_ota_runtime_hook*attach-test*)
            log_event "hook child identity confirmed pid=$HOOK_PID mode=$MODE"
            ;;
        *)
            terminal_exit failed hook-child 35 hook_identity_mismatch \
                "Live hook PID does not match staged runtime hook $MODE command." "$HOOK_PID"
            ;;
    esac
fi

write_status running "$RUN_PHASE" false 50 "" "$RUN_DETAIL" "$HOOK_PID" \
    || terminal_exit failed status 23 status_write_failed "Could not publish hook execution status." "$HOOK_PID"

HOOK_RC=0
wait "$HOOK_PID" || HOOK_RC=$?
log_event "hook child ended pid=$HOOK_PID mode=$MODE rc=$HOOK_RC"

if test "$HOOK_RC" = 0 && grep -q "\"phase\":\"$OK_HOOK_PHASE\"" "$HOOK_STATUS" 2>/dev/null; then
    terminal_exit completed "$OK_PHASE" 0 "" "$OK_DETAIL" "$HOOK_PID"
fi

FAIL_RC=$HOOK_RC
test "$FAIL_RC" != 0 || FAIL_RC=36
terminal_exit failed "$FAIL_PHASE" "$FAIL_RC" "$FAIL_REASON" \
    "$FAIL_DETAIL (rc=$HOOK_RC); inspect hook-status.json and hook.log." "$HOOK_PID"
