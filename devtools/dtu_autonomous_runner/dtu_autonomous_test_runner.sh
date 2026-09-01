#!/system/bin/sh

# Minimal persistence test for the PHNIX LTE modem. This deliberately performs
# no OTA operation, service control, hook installation, or firmware change.

TEST_DIR=/data/foxair_autonomous_test
STATUS_FILE="$TEST_DIR/status.json"
STATUS_TMP="$TEST_DIR/status.json.tmp.$$"
PID_FILE="$TEST_DIR/runner.pid"
LOG_FILE="$TEST_DIR/runner.log"

mkdir -p "$TEST_DIR" || exit 1
printf '%s\n' "$$" >"$PID_FILE" || exit 1

write_status() {
    state=$1
    step=$2
    now=$(date +%s)

    printf '{"state":"%s","step":%s,"pid":%s,"time":%s}\n' \
        "$state" "$step" "$$" "$now" >"$STATUS_TMP" || exit 1
    mv "$STATUS_TMP" "$STATUS_FILE" || exit 1
}

log_event() {
    printf '%s pid=%s %s\n' "$(date +%s)" "$$" "$1" >>"$LOG_FILE"
}

interrupt() {
    trap - TERM HUP INT
    write_status interrupted -1
    log_event interrupted
    exit 130
}

trap interrupt TERM HUP INT

write_status running 0
log_event started

step=1
while [ "$step" -le 24 ]; do
    sleep 5
    write_status running "$step"
    log_event "step=$step"
    step=$((step + 1))
done

write_status completed 24
log_event completed
exit 0
