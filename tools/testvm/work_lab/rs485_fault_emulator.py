#!/usr/bin/env python3
"""PHNIX board peer for a dynamically staged local OTA image."""

import argparse
import hashlib
import json
import os
import selectors
import time


DEVICE_INFO_REQUEST = bytes.fromhex("63 03 07 d1 00 5a 9c fe")
STATUS_HANDSHAKE_REQUEST = bytes.fromhex("63 03 00 06 00 01 6c 49")
PRODUCT_KEY_ACK = bytes.fromhex("63 10 00 c8 00 10 48 79")
DEVICE_ID = b"LABDEVICE001"
# V3.3 copies exactly eleven ProductKey bytes into a 32-byte FC10 block.  The
# remaining bytes are synthetic zero-initialised simulator padding; live data
# has not established that every board always clears this reserve area.
PRODUCT_KEY = b"a5cVutQfC8x" + bytes(21)
C350_CONFIRM = bytes.fromhex("63 10 C3 50 00 01 02 00 00 E8 6E")
C357_CONFIRM = bytes.fromhex("63 10 C3 57 00 01 02 00 00 E9 D9")
C36E_STATUS_1 = bytes.fromhex("63 10 C3 6E 00 03 06 00 63 00 01 00 A8 65 18")
C36E_STATUS_2 = bytes.fromhex("63 10 C3 6E 00 03 06 00 63 00 02 00 A8 95 18")
C36E_STATUS_3 = bytes.fromhex("63 10 C3 6E 00 03 06 00 63 00 03 00 A8 C4 D8")
C36E_STATUS_5 = bytes.fromhex("63 10 C3 6E 00 03 06 00 63 00 05 00 A8 24 D9")
TIMING_PROFILES = {
    # Existing developer-friendly behavior.
    "fast": {
        "minimum_block_period": 0.0,
        "staging_verify": 3.0,
        "status_visible": 3.0,
        "promotion": 12.0,
    },
    # Measured V3.3 -> V3.4 live update on 2026-08-28:
    # C5A8 28:56, final ACK -> status 3 about 2 s, status 3 -> status 5 about 5:14.
    "real-v34": {
        "minimum_block_period": 1736.0 / 1725.0,
        "staging_verify": 2.0,
        "status_visible": 3.0,
        "promotion": 311.0,
    },
}


def crc16_modbus(data: bytes) -> bytes:
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes((crc & 0xFF, crc >> 8))


def frame_with_crc(data: bytes) -> bytes:
    return data + crc16_modbus(data)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--peer", required=True)
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--from-app", required=True)
    parser.add_argument("--to-app", required=True)
    parser.add_argument(
        "--v33-ota-handshake", action="store_true",
        help="enable only C350/C357 confirmations and C36E statuses 1/2; no block ACKs",
    )
    parser.add_argument(
        "--v33-full-transfer", action="store_true",
        help="validate every C5A8 block and ACK it; emulator never flashes",
    )
    parser.add_argument("--firmware", help="firmware staged by the updater; loaded after C357")
    parser.add_argument("--board-version", default="0033", help="installed four-digit wire version")
    parser.add_argument(
        "--timing-profile", default="fast", choices=tuple(TIMING_PROFILES),
        help="fast developer timing or measured V3.4 live-update timing",
    )
    parser.add_argument("--resume-state", help="persist next confirmed C5A8 block across LTE restarts")
    parser.add_argument(
        "--fault-scenario", default="success",
        choices=("success", "c350-status0", "no-c350-status", "no-c357-status",
                 "no-block-ack", "wrong-block-ack", "wrong-ssid-ack", "drop-first-block-ack"),
    )
    parser.add_argument("--cancel-ack", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    timing = TIMING_PROFILES[args.timing_profile]
    if args.v33_full_transfer and not args.firmware:
        raise SystemExit("--v33-full-transfer requires --firmware")
    expected_firmware = b""
    offered_version = ""
    offered_size = 0
    offered_md5 = ""
    total_blocks = 0
    fd = os.open(args.peer, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    selector = selectors.DefaultSelector()
    selector.register(fd, selectors.EVENT_READ)
    pending = bytearray()
    device_id_sent = False
    product_key_sent = False
    c350_done = False
    c357_done = False
    next_block = 1
    if args.resume_state and os.path.exists(args.resume_state):
        with open(args.resume_state, "r", encoding="utf-8") as state_file:
            resume = json.load(state_file)
        next_block = int(resume.get("next_block", 1))
        if next_block < 1:
            raise SystemExit(f"invalid persisted next_block: {next_block}")
    first_block_seen = 0
    reconstructed = bytearray()
    completion_state = "transfer"
    last_c5a8_seen_at = None
    with open(args.transcript, "a", encoding="utf-8", buffering=1) as transcript, \
         open(args.from_app, "ab", buffering=0) as from_app, \
         open(args.to_app, "ab", buffering=0) as to_app:
        if args.v33_full_transfer:
            mode = (
                "dynamic validated OTA simulation; C5A8 ACK, status 3/5, "
                "promotion and commit enabled"
            )
        elif args.v33_ota_handshake:
            mode = "dynamic handshake only; C5A8 ACK disabled"
        else:
            mode = "identity-only; OTA disabled"
        transcript.write(
            f"{time.time():.6f} START {mode}; timing={args.timing_profile} "
            f"block-period-min={timing['minimum_block_period']:.3f}s "
            f"staging={timing['staging_verify']:.0f}s "
            f"promotion-total={timing['status_visible'] + timing['promotion']:.0f}s\n"
        )
        while True:
            for _, _ in selector.select(timeout=0.25):
                try:
                    # A C5A8 block is 183 bytes.  Capping reads at one frame
                    # prevents multiple complete frames from remaining in
                    # `pending` while both peers wait for the next C371 ACK.
                    data = os.read(fd, 183)
                except BlockingIOError:
                    continue
                if not data:
                    continue
                from_app.write(data)
                pending.extend(data)
                transcript.write(f"{time.time():.6f} DTU -> BOARD {data.hex(' ')}\n")
                if not device_id_sent and DEVICE_INFO_REQUEST in pending:
                    board_data = DEVICE_ID + bytes(180 - len(DEVICE_ID))
                    device_response = frame_with_crc(b"\x63\x03\xb4" + board_data)
                    os.write(fd, device_response)
                    to_app.write(device_response)
                    transcript.write(
                        f"{time.time():.6f} BOARD -> DTU device-id-response "
                        f"len={len(device_response)}\n"
                    )
                    device_id_sent = True
                    pending.clear()
                elif device_id_sent and DEVICE_INFO_REQUEST in pending:
                    # Cloud-originated and cyclic status reads use the same
                    # FC03 request after initial board discovery.  Reply while
                    # an OTA is active as the physical board would; this lets
                    # tests observe whether phnixIot4G safely interleaves it.
                    board_data = DEVICE_ID + bytes(180 - len(DEVICE_ID))
                    device_response = frame_with_crc(b"\x63\x03\xb4" + board_data)
                    os.write(fd, device_response)
                    to_app.write(device_response)
                    transcript.write(
                        f"{time.time():.6f} BOARD -> DTU status-block-response "
                        f"during={completion_state} len={len(device_response)}\n"
                    )
                    pending.clear()
                elif device_id_sent and STATUS_HANDSHAKE_REQUEST in pending:
                    # Register 0x0006 is a vendor command, not a conventional
                    # holding-register value.  It triggers this unsolicited
                    # FC10 ProductKey push and has no FC03 response frame.
                    product_frame = frame_with_crc(
                        b"\x63\x10\x00\xc8\x00\x10\x20" + PRODUCT_KEY
                    )
                    os.write(fd, product_frame)
                    to_app.write(product_frame)
                    transcript.write(
                        f"{time.time():.6f} BOARD -> DTU product-key-frame "
                        f"trigger=fc03-0006 len={len(product_frame)} "
                        f"{product_frame.hex(' ')}\n"
                    )
                    product_key_sent = True
                    pending.clear()
                elif PRODUCT_KEY_ACK in pending:
                    transcript.write(
                        f"{time.time():.6f} DTU -> BOARD product-key-ack "
                        f"{PRODUCT_KEY_ACK.hex(' ')}\n"
                    )
                    pending.clear()
                elif ((args.v33_ota_handshake or args.v33_full_transfer) and not c350_done
                      and b"\x63\x10\xc3\x50" in pending):
                    marker = pending.find(b"\x63\x10\xc3\x50")
                    if marker:
                        del pending[:marker]
                    if len(pending) < 23:
                        continue
                    request = bytes(pending[:23])
                    if request[6] != 14 or crc16_modbus(request[:-2]) != request[-2:]:
                        raise RuntimeError("invalid C350 update offer")
                    offered_ssid = int.from_bytes(request[7:9], "big")
                    offered_code = request[9:17].decode("ascii")
                    offered_version = request[17:21].decode("ascii")
                    transcript.write(
                        f"{time.time():.6f} PARSED c350 ssid={offered_ssid:04d} "
                        f"softwareCode={offered_code} version={offered_version} "
                        f"boardVersion={args.board_version}\n"
                    )
                    if args.fault_scenario == "no-c350-status":
                        os.write(fd, C350_CONFIRM)
                        to_app.write(C350_CONFIRM)
                        transcript.write(f"{time.time():.6f} BOARD -> DTU c350-confirm-only; status deliberately omitted\n")
                        c350_done = True
                        pending.clear()
                        continue
                    status_frame = C36E_STATUS_1
                    status_label = "c36e-status-1-block-168"
                    if args.fault_scenario == "c350-status0" or offered_version == args.board_version:
                        status_frame = frame_with_crc(bytes.fromhex("63 10 C3 6E 00 02 04 00 63 00 00"))
                        status_label = "c36e-status-0"
                    for label, response in (
                        ("c350-minimal-confirm", C350_CONFIRM),
                        (status_label, status_frame),
                    ):
                        os.write(fd, response)
                        to_app.write(response)
                        transcript.write(
                            f"{time.time():.6f} BOARD -> DTU {label} {response.hex(' ')}\n"
                        )
                        # The original UART receive path treats one read as one
                        # Modbus frame; keep replies out of the same PTY read.
                        time.sleep(1.0)
                    c350_done = True
                    pending.clear()
                elif ((args.v33_ota_handshake or args.v33_full_transfer) and c350_done
                      and not c357_done and b"\x63\x10\xc3\x57" in pending):
                    marker = pending.find(b"\x63\x10\xc3\x57")
                    if marker:
                        del pending[:marker]
                    if len(pending) < 47:
                        continue
                    request = bytes(pending[:47])
                    if request[6] != 38 or crc16_modbus(request[:-2]) != request[-2:]:
                        raise RuntimeError("invalid C357 firmware metadata")
                    offered_size = int.from_bytes(request[9:13], "big")
                    offered_md5 = request[13:45].decode("ascii").lower()
                    with open(args.firmware, "rb") as fixture:
                        expected_firmware = fixture.read()
                    actual_md5 = hashlib.md5(expected_firmware).hexdigest()
                    if len(expected_firmware) != offered_size or actual_md5 != offered_md5:
                        raise RuntimeError(
                            f"staged firmware differs from C357: size={len(expected_firmware)}/{offered_size} "
                            f"md5={actual_md5}/{offered_md5}"
                        )
                    total_blocks = (offered_size + 167) // 168
                    if next_block > total_blocks:
                        raise RuntimeError(f"persisted block {next_block} exceeds total {total_blocks}")
                    reconstructed = bytearray(expected_firmware[:(next_block - 1) * 168])
                    transcript.write(
                        f"{time.time():.6f} PARSED c357 size={offered_size} md5={offered_md5} "
                        f"blocks={total_blocks}\n"
                    )
                    if args.fault_scenario == "no-c357-status":
                        os.write(fd, C357_CONFIRM)
                        to_app.write(C357_CONFIRM)
                        transcript.write(f"{time.time():.6f} BOARD -> DTU c357-confirm-only; status deliberately omitted\n")
                        c357_done = True
                        pending.clear()
                        continue
                    for label, response in (
                        ("c357-minimal-confirm", C357_CONFIRM),
                        ("c36e-status-2-block-168", C36E_STATUS_2),
                    ):
                        os.write(fd, response)
                        to_app.write(response)
                        transcript.write(
                            f"{time.time():.6f} BOARD -> DTU {label} {response.hex(' ')}\n"
                        )
                        time.sleep(1.0)
                    c357_done = True
                    pending.clear()
                elif args.cancel_ack and b"\x63\x10\xc3\x6a" in pending:
                    cancel = frame_with_crc(bytes.fromhex("63 10 C3 6C 00 02 04 00 63 00 01"))
                    os.write(fd, cancel)
                    to_app.write(cancel)
                    transcript.write(f"{time.time():.6f} BOARD -> DTU c36c-cancel-ack {cancel.hex(' ')}\n")
                    pending.clear()
                elif completion_state in {"wait-status3-ack", "wait-status5-ack"} and b"\x63\x10\xc3\x7b" in pending:
                    transcript.write(
                        f"{time.time():.6f} DTU -> BOARD c37b-status-ack "
                        f"for={completion_state} {pending.hex(' ')}\n"
                    )
                    pending.clear()
                    if completion_state == "wait-status3-ack":
                        # Keep Status 3 visible for at least one 2-second host
                        # poll before promotion begins.
                        time.sleep(timing["status_visible"])
                        transcript.write(
                            f"{time.time():.6f} PHASE promotion-start "
                            f"duration={timing['promotion']:.0f}s\n"
                        )
                        time.sleep(timing["promotion"])
                        os.write(fd, C36E_STATUS_5)
                        to_app.write(C36E_STATUS_5)
                        transcript.write(
                            f"{time.time():.6f} BOARD -> DTU c36e-status-5 "
                            f"{C36E_STATUS_5.hex(' ')}\n"
                        )
                        completion_state = "wait-status5-ack"
                    else:
                        completion_state = "complete"
                        transcript.write(
                            f"{time.time():.6f} VERIFIED promotion status=5 acked; "
                            "staging-md5=ok copy=simulated target-md5=ok commit=simulated\n"
                        )
                elif args.v33_full_transfer and c357_done:
                    marker = pending.find(b"\x63\x10\xc5\xa8")
                    if marker < 0:
                        if len(pending) > 8192:
                            del pending[:-3]
                        continue
                    if marker:
                        del pending[:marker]
                    if len(pending) < 7:
                        continue
                    block_size = pending[6]
                    frame_len = 13 + block_size + 2
                    if len(pending) < frame_len:
                        continue
                    frame = bytes(pending[:frame_len])
                    del pending[:frame_len]
                    if crc16_modbus(frame[:-2]) != frame[-2:]:
                        raise RuntimeError(f"bad C5A8 CRC at block {next_block}")
                    ssid = int.from_bytes(frame[7:9], "big")
                    total = int.from_bytes(frame[9:11], "big")
                    block = int.from_bytes(frame[11:13], "big")
                    if completion_state in {"wait-status3-ack", "wait-status5-ack"} and block == total_blocks:
                        retry_ack = frame_with_crc(
                            b"\x63\x10\xc3\x71\x00\x04\x08\x00\x63\x00\x01\x00\x02"
                            + block.to_bytes(2, "big")
                        )
                        os.write(fd, retry_ack)
                        to_app.write(retry_ack)
                        transcript.write(
                            f"{time.time():.6f} BOARD -> DTU c371-ack retry "
                            f"block={block}/{total} ackB=2\n"
                        )
                        retry_status = (
                            C36E_STATUS_3 if completion_state == "wait-status3-ack"
                            else C36E_STATUS_5
                        )
                        time.sleep(timing["staging_verify"])
                        os.write(fd, retry_status)
                        to_app.write(retry_status)
                        transcript.write(
                            f"{time.time():.6f} BOARD -> DTU "
                            f"c36e-status-{'3' if completion_state == 'wait-status3-ack' else '5'} retry "
                            f"{retry_status.hex(' ')}\n"
                        )
                        continue
                    if (
                        args.fault_scenario in {"success", "drop-first-block-ack"}
                        and (ssid, total, block_size) == (0x63, total_blocks, 168)
                        and block == next_block - 1
                    ):
                        # The original service can repeat the most recently
                        # confirmed block when it has not consumed C371 before
                        # its retry tick. A physical board simply repeats the
                        # same ACK. Revalidate the bytes, but do not append or
                        # advance the persisted offset a second time.
                        duplicate_payload = frame[13:13 + block_size]
                        duplicate_start = (block - 1) * block_size
                        duplicate_expected = expected_firmware[
                            duplicate_start:duplicate_start + block_size
                        ]
                        duplicate_padded = duplicate_expected + b"\xff" * (
                            block_size - len(duplicate_expected)
                        )
                        if duplicate_payload != duplicate_padded:
                            raise RuntimeError(
                                f"firmware mismatch in repeated block {block}"
                            )
                        duplicate_ack_b = 2 if block == total else 1
                        duplicate_ack = frame_with_crc(
                            b"\x63\x10\xc3\x71\x00\x04\x08\x00\x63\x00\x01"
                            + duplicate_ack_b.to_bytes(2, "big")
                            + block.to_bytes(2, "big")
                        )
                        os.write(fd, duplicate_ack)
                        to_app.write(duplicate_ack)
                        transcript.write(
                            f"{time.time():.6f} BOARD -> DTU c371-ack repeated "
                            f"block={block}/{total} ackB={duplicate_ack_b} "
                            f"expected_next={next_block} offset_unchanged="
                            f"{(next_block - 1) * 168}\n"
                        )
                        continue
                    if (ssid, total, block, block_size) != (0x63, total_blocks, next_block, 168):
                        raise RuntimeError(
                            f"bad C5A8 header: ssid={ssid} total={total} block={block} "
                            f"size={block_size} expected_block={next_block}"
                        )
                    payload = frame[13:13 + block_size]
                    start = (block - 1) * block_size
                    expected = expected_firmware[start:start + block_size]
                    expected_padded = expected + b"\xff" * (block_size - len(expected))
                    if payload != expected_padded:
                        raise RuntimeError(f"firmware mismatch at block {block}")
                    reconstructed.extend(payload[:len(expected)])
                    # The original normal acceptance path uses ackB=1 even for
                    # the short final block. This advances 287448 by the full
                    # negotiated 168 bytes to the persisted EOF offset 287616.
                    first_block_seen += 1 if block == 1 else 0
                    if args.fault_scenario == "no-block-ack":
                        transcript.write(f"{time.time():.6f} FAULT no ACK for block={block}\n")
                        pending.clear()
                        continue
                    if args.fault_scenario == "drop-first-block-ack" and block == 1 and first_block_seen == 1:
                        transcript.write(f"{time.time():.6f} FAULT first ACK for block=1 dropped\n")
                        pending.clear()
                        continue
                    ack_b = 2 if block == total else 1
                    ack_block = block
                    ack_ssid = 0x63
                    if args.fault_scenario == "wrong-block-ack":
                        ack_block = block + 1
                    if args.fault_scenario == "wrong-ssid-ack":
                        ack_ssid = 0x64
                    ack_data = (
                        b"\x63\x10\xc3\x71\x00\x04\x08" + ack_ssid.to_bytes(2, "big") + b"\x00\x01"
                        + ack_b.to_bytes(2, "big") + ack_block.to_bytes(2, "big")
                    )
                    ack = frame_with_crc(ack_data)
                    block_seen_at = time.monotonic()
                    if last_c5a8_seen_at is not None:
                        remaining = (
                            last_c5a8_seen_at + timing["minimum_block_period"]
                            - block_seen_at
                        )
                        if remaining > 0:
                            time.sleep(remaining)
                    last_c5a8_seen_at = block_seen_at
                    os.write(fd, ack)
                    to_app.write(ack)
                    if args.resume_state:
                        state_tmp = args.resume_state + ".new"
                        with open(state_tmp, "w", encoding="utf-8") as state_file:
                            json.dump({"next_block": block + 1, "confirmed_offset": block * 168}, state_file)
                            state_file.flush()
                            os.fsync(state_file.fileno())
                        os.replace(state_tmp, args.resume_state)
                    if block == 1 or block % 100 == 0 or block == total:
                        transcript.write(
                            f"{time.time():.6f} BOARD -> DTU c371-ack block={block}/{total} "
                            f"ackB={ack_b} reconstructed={len(reconstructed)}\n"
                        )
                    if block == total:
                        digest = hashlib.sha256(reconstructed).hexdigest().upper()
                        if reconstructed != expected_firmware:
                            raise RuntimeError("final reconstructed firmware mismatch")
                        real_last_bytes = offered_size - start
                        if len(expected) != real_last_bytes or payload[real_last_bytes:] != b"\xff" * (168-real_last_bytes):
                            raise RuntimeError("unexpected final-block offset/length/padding")
                        transcript.write(
                            f"{time.time():.6f} VERIFIED final-block offset_before={start} "
                            f"real_bytes={len(expected)} ff_padding={block_size-len(expected)} "
                            f"offset_after_ack={start+block_size} ackB={ack_b}\n"
                            f"{time.time():.6f} VERIFIED transfer-complete bytes={len(reconstructed)} "
                            f"sha256={digest}; awaiting status 3/5 acknowledgements\n"
                        )
                        transcript.write(
                            f"{time.time():.6f} PHASE staging-verification-start "
                            f"duration={timing['staging_verify']:.0f}s\n"
                        )
                        time.sleep(timing["staging_verify"])
                        os.write(fd, C36E_STATUS_3)
                        to_app.write(C36E_STATUS_3)
                        transcript.write(
                            f"{time.time():.6f} BOARD -> DTU c36e-status-3 "
                            f"{C36E_STATUS_3.hex(' ')}\n"
                        )
                        completion_state = "wait-status3-ack"
                    next_block += 1
                elif len(pending) > 8192:
                    del pending[:-256]


if __name__ == "__main__":
    main()
