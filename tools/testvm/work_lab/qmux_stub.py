#!/usr/bin/env python3
"""Minimal, observable QMUX stream endpoint for the isolated PHNIX lab."""

import argparse
import selectors
import socket
import struct
import time
from pathlib import Path


RESULT_SUCCESS = b"\x02\x04\x00\x00\x00\x00\x00"


def tlv(kind: int, value: bytes) -> bytes:
    return bytes((kind,)) + struct.pack("<H", len(value)) + value


def low_nibble_bcd(digits: str) -> bytes:
    if len(digits) % 2:
        digits += "F"
    return bytes(int(digits[index + 1] + digits[index], 16) for index in range(0, len(digits), 2))


def ef_imsi(digits: str) -> bytes:
    """Build the standard EF_IMSI payload (length, parity/type, BCD digits)."""
    if not digits or not digits.isdigit():
        raise ValueError("IMSI must contain decimal digits")
    remainder = low_nibble_bcd(digits[1:])
    body = bytes(((int(digits[0]) << 4) | (9 if len(digits) % 2 else 1),)) + remainder
    return bytes((len(body),)) + body


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--binary-log", required=True)
    parser.add_argument("--server-binary-log", required=True)
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--client-id", type=lambda value: int(value, 0))
    parser.add_argument("--reply-first-sanitized-echo", action="store_true")
    parser.add_argument("--reply-init-profile", action="store_true")
    parser.add_argument("--iccid", default="89999000000000000001")
    parser.add_argument("--imsi", default="999990000000001")
    return parser.parse_args()


def platform_response(frame: bytes, qmi: bytes) -> bytes:
    response = bytearray(frame[:40] + qmi)
    struct.pack_into("<I", response, 0, len(response))
    return bytes(response)


def qmi_response(frame: bytes, msg_id: int, transaction_id: int, tlvs: bytes) -> bytes:
    qmi = struct.pack("<BHHH", 2, transaction_id, msg_id, len(tlvs)) + tlvs
    return platform_response(frame, qmi)


def build_init_profile_response(frame: bytes):
    msg_id = struct.unpack_from("<I", frame, 8)[0]
    response = bytearray(frame[:40] + bytes(len(frame) - 40))
    if msg_id == 4:
        return bytes(response), "init-success"
    if msg_id == 1:
        response[40] = 1
        return bytes(response), "allocated-service-client-id-1"
    if msg_id == 10:
        service_count = 60
        struct.pack_into("<I", response, 40, service_count)
        versions = {2: (1, 57), 3: (1, 158), 11: (1, 54)}
        for service_id in range(service_count):
            major, minor = versions.get(service_id, (1, 1))
            struct.pack_into("<BBHH", response, 44 + service_id * 6, service_id, 0, major, minor)
        return bytes(response), "version-list-with-dms-nas-uim-build-versions"
    return None


def build_qmi_service_response(frame: bytes, iccid: str, imsi: str):
    if len(frame) < 47 or struct.unpack_from("<I", frame, 8)[0] != 0:
        return None
    service_id = struct.unpack_from("<I", frame, 32)[0]
    qmi_flags = frame[40]
    transaction_id, msg_id, payload_len = struct.unpack_from("<HHH", frame, 41)
    if qmi_flags != 0 or len(frame) < 47 + payload_len:
        return None
    if service_id == 2 and msg_id == 0x25:
        imei = b"359762080000001"
        return qmi_response(frame, msg_id, transaction_id, RESULT_SUCCESS + tlv(0x11, imei)), \
            "dms-get-device-serial-numbers-synthetic-imei"
    if service_id == 3 and msg_id == 0x03:
        return qmi_response(frame, msg_id, transaction_id, RESULT_SUCCESS), "nas-indication-register-success"
    if service_id == 3 and msg_id == 0x24:
        serving_system = bytes((1, 1, 1, 2, 1, 8))
        return qmi_response(frame, msg_id, transaction_id, RESULT_SUCCESS + tlv(0x01, serving_system)), \
            "nas-serving-system-registered-lte"
    if service_id == 11 and msg_id == 0x2F:
        card_status = (
            struct.pack("<HHHH", 0, 0xFFFF, 0xFFFF, 0xFFFF)
            + bytes((1,))
            + bytes((1, 2, 3, 10, 0, 1))
            + bytes((2, 7, 0, 0, 0, 0, 0, 0, 2, 3, 10, 2, 3, 10))
        )
        return qmi_response(frame, msg_id, transaction_id, RESULT_SUCCESS + tlv(0x10, card_status)), \
            "uim-card-status-present-ready-usim"
    if service_id == 11 and msg_id == 0x47:
        # Get Slots Status: one present/active slot, logical slot 1 and a
        # low-nibble-first BCD ICCID. Variable array lengths are one byte.
        iccid_bcd = low_nibble_bcd(iccid)
        slot = struct.pack("<II", 2, 1) + bytes((1, len(iccid_bcd))) + iccid_bcd
        slots = bytes((1,)) + slot
        return qmi_response(frame, msg_id, transaction_id, RESULT_SUCCESS + tlv(0x10, slots)), \
            "uim-slots-status-synthetic-iccid"
    if service_id == 11 and msg_id == 0x20:
        # Read Transparent result. EF_IMSI exceeds an 8-bit QMI-IDL array
        # maximum in the schema, hence its on-wire length prefix is uint16.
        content = ef_imsi(imsi)
        read_result = struct.pack("<H", len(content)) + content
        return qmi_response(frame, msg_id, transaction_id, RESULT_SUCCESS + tlv(0x11, read_result)), \
            "uim-read-transparent-synthetic-imsi"
    return None


def main():
    args = parse_args()
    socket_path = Path(args.socket)
    if socket_path.exists() or socket_path.is_socket():
        socket_path.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen(8)
    server.setblocking(False)
    selector = selectors.DefaultSelector()
    selector.register(server, selectors.EVENT_READ, "listener")
    clients = {}

    with open(args.binary_log, "ab", buffering=0) as binary_log, \
         open(args.server_binary_log, "ab", buffering=0) as server_binary_log, \
         open(args.transcript, "a", encoding="utf-8", buffering=1) as transcript:
        transcript.write(f"{time.time():.6f} LISTEN {socket_path}\n")
        while True:
            for key, _ in selector.select(timeout=0.25):
                if key.data == "listener":
                    client, _ = server.accept()
                    client.setblocking(False)
                    clients[client.fileno()] = {"socket": client, "buffer": bytearray(), "replied": False}
                    selector.register(client, selectors.EVENT_READ, "client")
                    transcript.write(f"{time.time():.6f} ACCEPT fd={client.fileno()}\n")
                    if args.client_id is not None:
                        handshake = struct.pack("<I", args.client_id)
                        client.sendall(handshake)
                        server_binary_log.write(handshake)
                    continue
                client = key.fileobj
                state = clients[client.fileno()]
                data = client.recv(65535)
                if not data:
                    selector.unregister(client)
                    clients.pop(client.fileno(), None)
                    client.close()
                    continue
                binary_log.write(data)
                state["buffer"].extend(data)
                transcript.write(f"{time.time():.6f} CLIENT -> QMUX len={len(data)} hex-preview={data[:96].hex(' ')}\n")
                while len(state["buffer"]) >= 4:
                    frame_size = struct.unpack_from("<I", state["buffer"])[0]
                    if not 40 <= frame_size <= 1024 * 1024:
                        raise ValueError(f"invalid QMUX platform frame size: {frame_size}")
                    if len(state["buffer"]) < frame_size:
                        break
                    frame = bytes(state["buffer"][:frame_size])
                    del state["buffer"][:frame_size]
                    words = struct.unpack_from("<8I", frame, 8)
                    if args.reply_first_sanitized_echo and not state["replied"]:
                        response = frame[:40] + bytes(frame_size - 40)
                        client.sendall(response)
                        server_binary_log.write(response)
                        state["replied"] = True
                    if args.reply_init_profile:
                        built = build_init_profile_response(frame) or build_qmi_service_response(frame, args.iccid, args.imsi)
                        if built is not None:
                            response, description = built
                            client.sendall(response)
                            server_binary_log.write(response)
                            transcript.write(
                                f"{time.time():.6f} QMUX -> CLIENT profile={description} msg-id={words[0]} len={len(response)}\n"
                            )


if __name__ == "__main__":
    main()
