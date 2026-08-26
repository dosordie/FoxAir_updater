import json
import unittest
from pathlib import Path

from updater.common.phnix_traffic import (
    DEFAULT_HOOKS, HOOKS, EventRing, TrafficTracer, export_events, mask_secret,
    decode_payload, parse_gdb_trace, sanitize_fields,
)
from updater.common.phnix_frames import modbus_crc16

HELPER = Path("tools/phnix_traffic/foxair_traffic_trace")


class FakeGuardian:
    def poll(self): return None
    def wait(self, timeout=None): return 0
    def terminate(self): pass


class TrafficTest(unittest.TestCase):
    def test_full_tx_and_rx_payload_records(self):
        blob = b'{"cmd":"update"}' + b"\x01\x02\x03"
        raw = ("FOXBIN|mqtt|tx|user/update|16|0|0x1000\n"
               "FOXBIN|mqtt|rx|user/get|3|16|0x2000")
        rows = [json.loads(line) for line in parse_gdb_trace(raw, blob).splitlines()]
        self.assertEqual(rows[0]["payload_hex"], blob[:16].hex(" ").upper())
        self.assertEqual(rows[1]["payload_hex"], "01 02 03")
        self.assertEqual(rows[1]["length"], 3)

    def test_host_decoders_keep_raw_and_reuse_phnix_parser(self):
        body = bytes.fromhex("63 10 08 36 00 02 04 00 01 00 2D")
        frame = body + modbus_crc16(body).to_bytes(2, "little")
        kind, _text, fields = decode_payload(frame)
        self.assertEqual(kind, "phnix")
        self.assertEqual(fields["address_hex"], "0x0836")
        event = json.loads(parse_gdb_trace(
            f"FOXBIN|mqtt|tx|user/update|{len(frame)}|0|0x1", frame))
        self.assertEqual(event["payload_hex"], frame.hex(" ").upper())
        self.assertEqual(event["fields"]["values"][1]["value"], 0x2D)

    def test_json_and_unknown_binary_detection(self):
        kind, text, fields = decode_payload(b'{"deviceSecret":"abcdefgh","command":7}')
        self.assertEqual(kind, "json")
        self.assertIn("****efgh", text)
        self.assertEqual(fields["command"], 7)
        self.assertEqual(decode_payload(b"\x00\xff\x01")[0], "binary")

    def test_rx_hooks_dereference_message_length_and_payload(self):
        helper = HELPER.read_text(encoding="utf-8")
        self.assertIn("*(unsigned int *)($r2+4)+0x08", helper)
        self.assertIn("*(unsigned int *)($r2+4)+0x10", helper)
        self.assertIn("append binary memory", helper)
        self.assertNotIn("printf per byte", helper)

    def test_helper_uses_android_shebang_and_unix_line_endings(self):
        helper = HELPER.read_bytes()
        self.assertNotIn(b"\r\n", helper)
        self.assertEqual(helper.split(b"\n", 1)[0], b"#!/system/bin/sh")

    def test_secret_masking_contract(self):
        self.assertEqual(mask_secret(""), "nicht gesetzt")
        self.assertEqual(mask_secret("abcd"), "****")
        self.assertEqual(mask_secret("abcdefgh"), "****efgh")
        self.assertEqual(sanitize_fields({"deviceSecret": "abcdefgh"})["deviceSecret"], "****efgh")

    def test_trace_parser_rejects_bad_lengths(self):
        data = parse_gdb_trace("FOX|mqtt|tx|user/update|2|0x1234|63 10 \nFOX|mqtt|rx|ota|3|0x1|00")
        rows = data.splitlines()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0])["payload_hex"], "63 10")

    def test_ring_is_bounded_and_redacts_json(self):
        ring = EventRing(2)
        for number in range(3):
            ring.add_json_lines(json.dumps({
                "protocol": "https", "direction": "rx", "channel": "register",
                "length": 1, "payload_type": "json", "sensitive": True,
                "payload_text": json.dumps({"deviceSecret": "abcdefgh", "code": number}),
            }))
        self.assertEqual(len(ring.snapshot()), 2)
        self.assertIsNone(ring.snapshot()[-1].payload_text)
        self.assertNotIn("abcdefgh", export_events(ring.snapshot()))

    def test_every_ui_channel_has_a_parser_and_hook_fixture(self):
        raw = "\n".join((
            "FOX|mqtt|tx|user/update|2|0x1|63 10 ",
            "FOX|mqtt|rx|user/get|1|0x1|03 ",
            "FOX|mqtt|rx|ota|1|0x1|7b ",
            "FOX|mqtt|tx|ota_update|1|0x1|7d ",
            "META|ota_start|mainboard|/cache/phnixIot_device_OTA|https://example/fw.bin",
            "FOX|http|rx|ota_chunk|4096|0x1|",
            "META|provision|linked_go_queryiotdevice|http|120",
            "META|provision|legacy_queryiotdevice|http|80",
            "META|provision|linked_go_create_device_by_sign|http|0",
            "META|provision|aliyun_dynamic_register|https|0",
            "META|provision|aliyun_dynamic_register_response|https|0",
        ))
        channels = {json.loads(line)["channel"] for line in parse_gdb_trace(raw).splitlines()}
        self.assertEqual(channels, {"user/update", "user/get", "ota", "ota_update",
                                    "ota_download_start", "ota_chunk",
                                    "linked_go_queryiotdevice", "legacy_queryiotdevice",
                                    "linked_go_create_device_by_sign", "aliyun_dynamic_register",
                                    "aliyun_dynamic_register_response"})
        hook = Path("tools/phnix_traffic/foxair_traffic_trace").read_text(encoding="utf-8")
        for address in ("0x1F6FC", "0x1EED0", "0x1ED98", "0x1F9B0", "0x19A54",
                        "0x19E70", "0x19C18", "0x16960", "0x15C58", "0x164AC",
                        "0x22FF4", "0x22B9C"):
            self.assertIn(f"ADDR={address}", hook)

    def test_metadata_hook_records_never_contain_payload_bytes(self):
        parsed = json.loads(parse_gdb_trace(
            "FOX|hook_hit|mqtt_tx_update|len=123|ptr=0x4567"))
        self.assertEqual(parsed["channel"], "mqtt_tx_update")
        self.assertEqual(parsed["length"], 123)
        self.assertEqual(parsed["payload_type"], "metadata")
        self.assertIsNone(parsed["payload_hex"])

    def test_safe_default_is_exactly_one_mqtt_tx_hook(self):
        self.assertEqual(DEFAULT_HOOKS, ("mqtt_tx_update",))
        self.assertEqual(len(HOOKS), 12)

    def test_all_secret_spellings_are_removed_from_ring_and_export(self):
        secrets = {"DeviceSecret": "device-raw-secret", "ProductSecret": "product-raw-secret",
                   "sign": "raw-signature"}
        ring = EventRing()
        ring.add_json_lines(json.dumps({"protocol": "https", "direction": "rx",
            "channel": "aliyun_dynamic_register_response", "length": 12,
            "payload_type": "json", "payload_hex": "72 61 77", "payload_text": json.dumps(secrets),
            "fields": secrets, "sensitive": True}))
        exported = export_events(ring.snapshot())
        for raw in secrets.values():
            self.assertNotIn(raw, exported)
        self.assertNotIn("72 61 77", exported)

    def test_ota_download_metadata_and_dtu_target(self):
        rows = parse_gdb_trace("META|ota_start|dtu|/data/phnixIot4G_OTA|http://example/dtu")
        event = json.loads(rows)
        self.assertEqual(event["fields"]["download_type"], "dtu")
        self.assertEqual(event["fields"]["target"], "/data/phnixIot4G_OTA")

    def test_remote_log_is_read_incrementally_and_keeps_partial_line(self):
        class FakeAdb:
            def __init__(self):
                self.calls = []
                self.responses = [
                    "FOXAIR_SIZE:32\nFOX|mqtt|tx|user/update|1|0x1|",
                    "FOXAIR_SIZE:36\n63 \n",
                ]

            def run(self, *args):
                self.calls.append(args)
                return self.responses.pop(0)

        adb = FakeAdb()
        tracer = TrafficTracer(adb, "unused")
        self.assertEqual(tracer.events(), "")
        parsed = tracer.events()
        self.assertEqual(json.loads(parsed)["payload_hex"], "63")
        self.assertIn("skip=0", adb.calls[0][1])
        self.assertIn("skip=32", adb.calls[1][1])

    def test_enable_delegates_binary_verification_to_modem_helper(self):
        class FakeAdb:
            def __init__(self):
                self.pushed = False
                self.commands = []

            def push(self, *args):
                self.pushed = True
                self.commands.append(("push", args))

            def shell(self, command, check=True):
                self.commands.append(((command,), {}))
                return "active"

            def read_file(self, remote):
                raise AssertionError(f"unexpected diagnostic read: {remote}")

            def popen_shell(self, command):
                self.commands.append(("popen_shell", command))
                return FakeGuardian()

        adb = FakeAdb()
        self.assertEqual(TrafficTracer(adb, HELPER).enable(), "active")
        self.assertTrue(adb.pushed)
        self.assertNotIn("read_file", repr(adb.commands))
        self.assertTrue(any("foxair_traffic_trace serve" in repr(call) for call in adb.commands))

    def test_enable_rejects_crlf_helper_before_push(self):
        class FakeAdb:
            def push(self, *_args):
                raise AssertionError("CRLF helper must not be pushed")

        helper = Path(self.id() + ".tmp")
        try:
            helper.write_bytes(b"#!/system/bin/sh\r\necho broken\r\n")
            with self.assertRaisesRegex(ValueError, "CRLF"):
                TrafficTracer(FakeAdb(), helper).enable()
        finally:
            helper.unlink(missing_ok=True)

    def test_remote_helper_needs_no_elf_utilities_and_rechecks_before_attach(self):
        hook = Path("tools/phnix_traffic/foxair_traffic_trace").read_text(encoding="utf-8")
        self.assertNotIn("readelf", hook)
        self.assertNotIn("objdump", hook)
        self.assertIn('/bin/sha256sum "$BIN"', hook)
        self.assertIn("EXPECTED_SHA256=7c573431f0a67620d473419644a83a4f4dc04b8a91bde5923c74a63ba1eaedb7", hook)
        self.assertIn('readlink "/proc/$CHECK_PID/exe"', hook)
        self.assertIn('kill -0 "$CHECK_PID"', hook)
        self.assertIn('test -r "/proc/$CHECK_PID/maps"', hook)
        verify_calls = hook.count('verify_running_binary "$PID"')
        self.assertEqual(verify_calls, 2)
        self.assertLess(hook.rfind('verify_running_binary "$PID"'),
                        hook.index("gdbserver --attach"))

    def test_failed_enable_reads_both_debug_logs_without_purge(self):
        class FakeAdb:
            def __init__(self):
                self.commands = []

            def push(self, *args):
                self.commands.append(("push", args))

            def shell(self, command, check=True):
                self.commands.append(("shell", command, check))
                if command.endswith(" status; else echo inactive; fi"):
                    return "inactive"
                return ""

            def read_file(self, remote):
                self.commands.append(("read_file", remote))
                return ("failure from " + remote).encode()

            def popen_shell(self, command):
                self.commands.append(("popen_shell", command))
                return FakeGuardian()

        adb = FakeAdb()
        tracer = TrafficTracer(adb, HELPER)
        self.assertEqual(tracer.enable(), "inactive")
        self.assertIn("failure from /data/local/tmp/foxair-traffic/gdbserver.log",
                      tracer.startup_diagnostics)
        self.assertIn("failure from /data/local/tmp/foxair-traffic/gdb.log",
                      tracer.startup_diagnostics)
        self.assertFalse(any("--purge" in repr(command) for command in adb.commands))

    def test_helper_waits_for_both_debuggers_before_marking_active(self):
        hook = Path("tools/phnix_traffic/foxair_traffic_trace").read_text(encoding="utf-8")
        server_check = 'kill -0 "$(cat "$STATE/gdbserver.pid")"'
        gdb_check = 'kill -0 "$(cat "$STATE/gdb.pid")"'
        self.assertIn(server_check, hook)
        self.assertIn(gdb_check, hook)
        self.assertGreaterEqual(hook.count("sleep 1"), 2)
        self.assertLess(hook.index(server_check), hook.index("gdb -q -x"))
        self.assertLess(hook.index(gdb_check), hook.index('touch "$STATE/active"'))
        self.assertIn('startup_failed "gdbserver beendet"', hook)
        self.assertIn('startup_failed "gdb beendet"', hook)

    def test_helper_guards_debugger_stops_with_external_watchdogs(self):
        hook = HELPER.read_text(encoding="utf-8")
        self.assertIn("watchdog_pids > \"$WATCHDOG_PIDS\"", hook)
        self.assertIn('kill -STOP "$wd"', hook)
        self.assertIn('kill -CONT "$wd"', hook)
        self.assertIn("trap emergency_cleanup EXIT INT TERM", hook)
        self.assertLess(hook.index("freeze_watchdogs\n"),
                        hook.index("gdbserver --attach"))
        self.assertNotIn("resume_watchdogs\n  trap - EXIT INT TERM", hook)
        self.assertIn('watchdogs=guarded', hook)
        self.assertIn('MAX_TRACE_SECONDS=120', hook)
        self.assertIn('start|serve) shift; serve_trace "$@"', hook)
        self.assertIn('trap emergency_cleanup HUP INT TERM', hook)
        self.assertIn('test "$MAX_TRACE_SECONDS" -ge 15', hook)
        self.assertLess(hook.index('wait_service_running "$OLD_PID"'),
                        hook.index("resume_watchdogs\n  if test \"$STOP_OK\""))

    def test_gdb_lifecycle_matches_runtime_hook_initialization_and_detaches(self):
        hook = HELPER.read_text(encoding="utf-8")
        initialization = "\n".join((
            "set architecture arm", "set target-async on", "set pagination off", "set confirm off",
            "set print thread-events off", "set auto-load safe-path /",
            "set libthread-db-search-path /lib", "file /data/phnixIot4G",
            "set logging file /data/local/tmp/foxair-traffic/raw.log",
        ))
        self.assertIn(initialization, hook)
        self.assertIn('kill -TERM "$GDB_PID"', hook)
        self.assertIn('kill -TERM "$GDBSERVER_PID"', hook)
        self.assertIn('TRACER_PID=$(awk', hook)
        self.assertIn("set target-async on", hook)
        self.assertIn("printf 'continue&\\n' >&3", hook)
        self.assertIn('test "$SAME_PID" != "$OLD_PID"', hook)

    def test_each_run_isolated_and_cleanup_requires_confirmed_detach(self):
        hook = HELPER.read_text(encoding="utf-8")
        self.assertIn("set logging overwrite on", hook)
        self.assertNotIn("set logging overwrite off", hook)
        self.assertIn('ARCHIVE="$STATE/archive/$OLD_RUN_ID"', hook)
        self.assertIn('RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"', hook)
        self.assertIn('active|run_id=', hook)
        self.assertIn('critical|%s|run_id=%s|', hook)
        self.assertIn('FOX|detached|run_id=', hook)
        self.assertIn('GDB und gdbserver bleiben unangetastet', hook)
        self.assertIn('kill -TERM "$GDB_PID"', hook)

    def test_sigsegv_and_pid_change_are_critical_and_not_ignored(self):
        hook = HELPER.read_text(encoding="utf-8")
        self.assertIn("critical_failure sigsegv", hook)
        self.assertIn("critical_failure pid_changed", hook)
        self.assertNotIn("SIGSEGV nostop", hook)
        self.assertNotIn("handle SIGSEGV", hook)

    def test_helper_validates_selection_before_attach_and_cleans_markers(self):
        hook = HELPER.read_text(encoding="utf-8")
        self.assertLess(hook.index('test -n "$HOOKS"'), hook.index("gdbserver --attach"))
        self.assertLess(hook.index('for ID in $HOOKS'), hook.index("gdbserver --attach"))
        self.assertIn("Unbekannte Hook-ID", hook)
        self.assertIn('rm -f "$STATE/active" "$STATE/stopping" "$STATE/stop.request" "$STATE/guardian.pid"', hook)
        self.assertIn('"$STATE/gdb.pid" "$STATE/gdbserver.pid"', hook)
        self.assertNotIn('rm -f "$STATE/gdb.log"', hook)

    def test_enable_passes_only_selected_hook_ids(self):
        class FakeAdb:
            def __init__(self): self.commands = []
            def push(self, *_args): pass
            def shell(self, command, check=True):
                self.commands.append(command)
                return "active"
            def popen_shell(self, command):
                self.commands.append(command)
                return FakeGuardian()
        adb = FakeAdb()
        tracer = TrafficTracer(adb, HELPER)
        tracer.enable(("mqtt_rx_get", "http_ota_chunk"))
        start = next(command for command in adb.commands if " serve " in command)
        self.assertIn("--hook mqtt_rx_get", start)
        self.assertIn("--hook http_ota_chunk", start)
        self.assertNotIn("--hook mqtt_tx_update", start)

    def test_enable_rejects_empty_and_unknown_hook_sets_before_push(self):
        class FakeAdb:
            def push(self, *_args): raise AssertionError("must reject before push")
        tracer = TrafficTracer(FakeAdb(), HELPER)
        with self.assertRaisesRegex(ValueError, "Mindestens"):
            tracer.enable(())
        with self.assertRaisesRegex(ValueError, "Unbekannte"):
            tracer.enable(("not_a_hook",))


if __name__ == "__main__":
    unittest.main()
