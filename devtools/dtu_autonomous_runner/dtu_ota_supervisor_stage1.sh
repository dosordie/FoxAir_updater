#!/system/bin/sh

# Stage 1 of the autonomous DTU OTA supervisor.
#
# This intentionally performs NO OTA operation, NO service control, NO GDB
# attach, and NO firmware access.  It validates the lifecycle that the real
# updater will later use: one run at a time, detached execution, durable
# per-run status/logs, controlled abort requests, and explicit ack/cleanup.

umask 077

BASE_DIR=/data/foxair_ota_runner
RUNS_DIR="$BASE_DIR/runs"
LOCK_DIR="$BASE_DIR/active.lock"
LAST_RUN_FILE="$BASE_DIR/last_run_id"
RUNNER_NAME=dtu_ota_supervisor_stage1.sh

RUN_ID=${1:-}
case "$RUN_ID" in
    ''|*[!A-Za-z0-9._-]*)
        echo "ERROR: invalid run_id" >&2
        exit 2
        ;;
esac

RUN_DIR="$RUNS_DIR/$RUN_ID"
STATUS_FILE="$RUN_DIR/status.json"
STATUS_TMP="$RUN_DIR/status.json.tmp.$$"
PID_FILE="$RUN_DIR/runner.pid"
LOG_FILE="$RUN_DIR/runner.log"
ABORT_REQUEST="$RUN_DIR/abort.request"

mkdir -p "$RUN_DIR" || exit 3
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
    now=$(date +%s)
    ppid=$(runner_ppid)
    reason_json=$(json_escape "$reason")
    detail_json=$(json_escape "$detail")

    printf '{"schema":"foxair-dtu-runner-v1","run_id":"%s","state":"%s","phase":"%s","terminal":%s,"progress":%s,"pid":%s,"ppid":%s,"time":%s,"reason":"%s","detail":"%s"}\n' \
        "$RUN_ID" "$state" "$phase" "$terminal" "$progress" "$$" "$ppid" "$now" "$reason_json" "$detail_json" \
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
    write_status "$state" "$phase" true 100 "$reason" "$detail" || true
    log_event "terminal state=$state phase=$phase reason=$reason"
    release_lock
    exit "$rc"
}

signal_exit() {
    trap - TERM HUP INT
    terminal_exit aborted signal 130 signal_received "Runner received TERM/HUP/INT before any OTA functionality was enabled."
}

trap signal_exit TERM HUP INT

write_status starting lock false 0 "" "Acquiring single-run lock." || exit 3

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    owner=$(cat "$LOCK_DIR/run_id" 2>/dev/null || true)
    owner_pid=$(cat "$LOCK_DIR/pid" 2>/dev/null || true)
    write_status failed lock true 0 active_run_exists "Another run owns the DTU runner lock: run_id=$owner pid=$owner_pid" || true
    log_event "lock refused owner=$owner owner_pid=$owner_pid"
    exit 20
fi

printf '%s\n' "$RUN_ID" > "$LOCK_DIR/run_id" || terminal_exit failed lock 21 lock_write_failed "Could not persist lock owner."
printf '%s\n' "$$" > "$LOCK_DIR/pid" || terminal_exit failed lock 21 lock_write_failed "Could not persist lock PID."
printf '%s\n' "$RUN_ID" > "$LAST_RUN_FILE.tmp.$$" || terminal_exit failed bootstrap 22 last_run_write_failed "Could not write last_run_id."
mv "$LAST_RUN_FILE.tmp.$$" "$LAST_RUN_FILE" || terminal_exit failed bootstrap 22 last_run_write_failed "Could not atomically publish last_run_id."

log_event "started"
write_status running ready false 0 "" "Detached runner is active; stage 1 performs lifecycle self-test only." || terminal_exit failed status 23 status_write_failed "Could not publish initial status."

step=0
while test "$step" -lt 24; do
    if test -f "$ABORT_REQUEST"; then
        terminal_exit aborted abort-request 130 abort_requested "Controlled abort request accepted during stage-1 self-test."
    fi

    sleep 5
    step=$((step + 1))
    progress=$((step * 100 / 24))
    write_status running autonomous-selftest false "$progress" "" "Stage-1 autonomous lifecycle self-test is running." \
        || terminal_exit failed status 23 status_write_failed "Could not update status atomically."
    log_event "selftest step=$step progress=$progress"
done

terminal_exit completed completed 0 "" "Stage-1 autonomous lifecycle self-test completed successfully; status is retained until acknowledged and cleaned up."
