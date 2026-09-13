from pathlib import Path


RUNNER = Path("updater/dtu_ota/payload/dtu_ota_supervisor.sh")


def _runner_text() -> str:
    return RUNNER.read_text(encoding="utf-8")


def test_mqtt_gate_uses_adb_visible_tcp_state_and_stability_confirmation():
    runner = _runner_text()
    mqtt = runner.split("mqtt_established() {", 1)[1].split("wait_for_mqtt_ready() {", 1)[0]
    wait = runner.split("wait_for_mqtt_ready() {", 1)[1].split("restore_original_confirmed() {", 1)[0]

    assert "netstat -nt" in mqtt
    assert ":1883" in mqtt
    assert "ESTABLISHED" in mqtt
    assert "MQTT_READY_TIMEOUT=120" in runner
    assert "MQTT_READY_CONFIRM_DELAY=3" in runner
    assert 'test "$stable" -ge 2' in wait
    assert 'sleep "$confirm_delay"' in wait
    assert 'current=$(single_service_pid) || return 2' in wait
    assert 'test "$current" = "$SERVICE_PID" || return 2' in wait


def test_cloud_gate_runs_before_http_and_runtime_hook():
    runner = _runner_text()
    run = runner.split("run_action() {", 1)[1].split("classify_action() {", 1)[0]

    cloud_wait = run.index("service-cloud-wait")
    wait_call = run.index('wait_for_mqtt_ready "$MQTT_READY_TIMEOUT"')
    cloud_ready = run.index("service-cloud-ready")
    http_start = run.index("start_http")
    hook_start = run.index('"$SHELL_BIN" "$HOOK" $args')

    assert cloud_wait < wait_call < cloud_ready < http_start < hook_start
    assert "cloud_not_ready_before_hook" in run
    assert "service_unstable_before_hook" in run
    assert "no hook or OTA action was started" in run


def test_mqtt_gate_does_not_change_board_protocol_or_safety_boundary():
    runner = _runner_text()
    hook = Path("updater/dtu_ota/payload/phnix_ota_runtime_hook").read_text(encoding="utf-8")

    # The supervisor gate must remain outside the board protocol implementation.
    assert "wait_for_mqtt_ready" not in hook
    for marker in ("C350_SENT", "C357_SENT", "C5A8_SENT", "C36E_STATUS"):
        assert marker in runner
    assert "guarded_result" in runner
    assert "original-service-authoritative" in runner
