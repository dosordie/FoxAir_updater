from pathlib import Path


RUNNER = Path("updater/dtu_ota/payload/dtu_ota_supervisor.sh")


def _runner_text() -> str:
    return RUNNER.read_text(encoding="utf-8")


def test_readiness_gate_uses_internal_service_state_not_mqtt_socket():
    runner = _runner_text()
    probe = runner.split("read_process_u8() {", 1)[1].split("wait_for_service_ready() {", 1)[0]
    wait = runner.split("wait_for_service_ready() {", 1)[1].split("restore_original_confirmed() {", 1)[0]

    assert 'dd if="/proc/$pid/mem"' in probe
    assert "DTU_RUN_STEP_ADDR=624899" in runner  # 0x98903
    assert "DTU_STA_ADDR=624900" in runner  # 0x98904
    assert "BOARD_OTA_STEP_ADDR=625300" in runner  # 0x98a94
    assert "UART_SEND_FLAG_ADDR=602332" in runner  # 0x930dc
    assert "SERVICE_READY_TIMEOUT=120" in runner
    assert "SERVICE_READY_CONFIRM_DELAY=3" in runner
    assert 'test "$run_step" = 11' in wait
    assert 'test "$dtu_sta" = 4' in wait
    assert 'test "$board_step" = 12' in wait
    assert 'test "$uart_flag" = 0' in wait
    assert 'test "$stable" -ge 2' in wait
    assert "netstat -nt" not in probe
    assert "ESTABLISHED" not in probe


def test_local_ready_gate_runs_before_http_hook_and_optional_mqtt_isolation():
    runner = _runner_text()
    run = runner.split("run_action() {", 1)[1].split("classify_action() {", 1)[0]

    ready_wait = run.index("service-ready-wait")
    wait_call = run.index('wait_for_service_ready "$SERVICE_READY_TIMEOUT"')
    ready = run.index("service-ready", ready_wait + len("service-ready-wait"))
    http_start = run.index("start_http")
    isolate_arg = run.index('--isolate-mqtt')
    hook_start = run.index('"$SHELL_BIN" "$HOOK" $args')

    assert ready_wait < wait_call < ready < http_start < isolate_arg < hook_start
    assert "service_not_ready_before_hook" in run
    assert "service_state_unreadable_before_hook" in run
    assert "service_unstable_before_hook" in run
    assert "no hook or OTA action was started" in run


def test_local_gate_does_not_change_board_protocol_or_safety_boundary():
    runner = _runner_text()
    hook = Path("updater/dtu_ota/payload/phnix_ota_runtime_hook").read_text(encoding="utf-8")

    # Readiness is a supervisor-only pre-hook gate. The validated board protocol stays in the hook.
    assert "wait_for_service_ready" not in hook
    for marker in ("C350_SENT", "C357_SENT", "C5A8_SENT", "C36E_STATUS"):
        assert marker in runner
    assert "guarded_result" in runner
    assert "original-service-authoritative" in runner
