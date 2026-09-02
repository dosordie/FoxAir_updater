#!/usr/bin/env python3
"""Loopback TLS/MQTT recorder with a runtime one-shot control socket."""

import argparse
import json
import queue
import socket
import ssl
import struct
import threading
import time
from pathlib import Path


def read_exact(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.recv(size - len(data))
        if not chunk:
            raise EOFError
        data.extend(chunk)
    return bytes(data)


def read_packet(stream):
    first = read_exact(stream, 1)[0]
    multiplier = 1
    remaining = 0
    encoded = bytearray()
    for _ in range(4):
        value = read_exact(stream, 1)[0]
        encoded.append(value)
        remaining += (value & 0x7F) * multiplier
        if not value & 0x80:
            return first, bytes(encoded), read_exact(stream, remaining)
        multiplier *= 128
    raise ValueError("invalid MQTT remaining length")


def remaining_length(value):
    encoded = bytearray()
    while True:
        digit = value % 128
        value //= 128
        if value:
            digit |= 0x80
        encoded.append(digit)
        if not value:
            return bytes(encoded)


def mqtt_bytes(value):
    return struct.pack("!H", len(value)) + value


def mqtt_string(payload, offset):
    length = struct.unpack_from("!H", payload, offset)[0]
    offset += 2
    return payload[offset:offset + length].decode("utf-8", "replace"), offset + length


def decode_connect(payload):
    protocol, pos = mqtt_string(payload, 0)
    level, flags = payload[pos], payload[pos + 1]
    keepalive = struct.unpack_from("!H", payload, pos + 2)[0]
    pos += 4
    client_id, pos = mqtt_string(payload, pos)
    record = {"type": "CONNECT", "protocol": protocol, "level": level,
              "flags": flags, "keepalive": keepalive, "client_id": client_id}
    if flags & 0x04:
        record["will_topic"], pos = mqtt_string(payload, pos)
        _, pos = mqtt_string(payload, pos)
    if flags & 0x80:
        record["username"], pos = mqtt_string(payload, pos)
    if flags & 0x40:
        password, pos = mqtt_string(payload, pos)
        record.update(password_length=len(password), password_redacted=True)
    return record


def decode_subscribe(first, payload):
    packet_id = struct.unpack_from("!H", payload, 0)[0]
    pos = 2
    topics = []
    while pos < len(payload):
        topic, pos = mqtt_string(payload, pos)
        qos = payload[pos]
        pos += 1
        topics.append({"topic": topic, "qos": qos})
    return {"type": "SUBSCRIBE", "packet_id": packet_id,
            "dup": bool(first & 0x08), "topics": topics}


def decode_publish(first, payload):
    topic, pos = mqtt_string(payload, 0)
    qos = (first >> 1) & 0x03
    packet_id = None
    if qos:
        packet_id = struct.unpack_from("!H", payload, pos)[0]
        pos += 2
    body = payload[pos:]
    return {"type": "PUBLISH", "topic": topic, "qos": qos,
            "dup": bool(first & 0x08), "retain": bool(first & 0x01),
            "packet_id": packet_id, "payload_length": len(body),
            "payload": body.decode("utf-8", "replace"),
            "payload_hex": body.hex()}


def log_record(path, record):
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"time": time.time(), **record}, ensure_ascii=False) + "\n")


def control_server(path, requests, transcript):
    control = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    path.unlink(missing_ok=True)
    control.bind(str(path))
    path.chmod(0o660)
    control.listen(4)
    log_record(transcript, {"type": "CONTROL_LISTEN", "path": str(path)})
    try:
        while True:
            client, _ = control.accept()
            with client:
                try:
                    request = json.loads(client.recv(65536).decode("utf-8"))
                    topic = str(request["topic"])
                    payload = bytes.fromhex(str(request["payload_hex"]))
                    if len(payload) > 4096:
                        raise ValueError("payload exceeds 4096-byte lab limit")
                    label = str(request.get("label", "runtime-one-shot"))
                    requests.put((topic, payload, label))
                    client.sendall(b"MQTT-One-Shot eingereiht\n")
                    log_record(transcript, {"type": "CONTROL_QUEUED", "topic": topic,
                                            "label": label, "payload_hex": payload.hex()})
                except (KeyError, ValueError, json.JSONDecodeError) as error:
                    client.sendall((f"FEHLER: {error}\n").encode())
    finally:
        control.close()
        path.unlink(missing_ok=True)


def send_probe(stream, topic, payload, packet_id, transcript, kind, label=""):
    variable = mqtt_bytes(topic.encode()) + struct.pack("!H", packet_id)
    packet = variable + payload
    stream.sendall(b"\x32" + remaining_length(len(packet)) + packet)
    log_record(transcript, {"type": kind, "topic": topic, "qos": 1,
                            "packet_id": packet_id, "label": label,
                            "payload_hex": payload.hex()})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--binary-log", required=True)
    parser.add_argument("--control-socket")
    parser.add_argument("--probe-topic")
    parser.add_argument("--probe-payload-hex")
    parser.add_argument("--probe-payload-file")
    parser.add_argument("--scheduled-probe", action="append", default=[], metavar="SECONDS:FILE")
    args = parser.parse_args()

    runtime_requests = queue.Queue()
    if args.control_socket:
        thread = threading.Thread(
            target=control_server,
            args=(Path(args.control_socket), runtime_requests, args.transcript),
            daemon=True,
        )
        thread.start()

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(args.cert, args.key)
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 1883))
    listener.listen(4)
    log_record(args.transcript, {"type": "LISTEN", "address": "127.0.0.1:1883"})

    while True:
        raw, peer = listener.accept()
        probe_sent = False
        scheduled = []
        pending_runtime = []
        subscribed = set()
        next_packet_id = 0x7100
        try:
            with context.wrap_socket(raw, server_side=True) as stream:
                stream.settimeout(0.10)
                log_record(args.transcript, {"type": "TLS", "peer": list(peer),
                                              "version": stream.version(),
                                              "cipher": stream.cipher()[0]})
                while True:
                    while True:
                        try:
                            pending_runtime.append(runtime_requests.get_nowait())
                        except queue.Empty:
                            break
                    unsent = []
                    for topic, probe, label in pending_runtime:
                        if topic not in subscribed:
                            unsent.append((topic, probe, label))
                            continue
                        send_probe(stream, topic, probe, next_packet_id, args.transcript,
                                   "LAB_RUNTIME_PROBE_SENT", label)
                        next_packet_id += 1
                    pending_runtime = unsent
                    now = time.monotonic()
                    while scheduled and scheduled[0][0] <= now:
                        _, probe_path = scheduled.pop(0)
                        probe = Path(probe_path).read_bytes().rstrip(b"\r\n")
                        send_probe(stream, args.probe_topic, probe, next_packet_id,
                                   args.transcript, "LAB_SCHEDULED_PROBE_SENT", probe_path)
                        next_packet_id += 1
                    try:
                        first, encoded, payload = read_packet(stream)
                    except socket.timeout:
                        continue
                    with open(args.binary_log, "ab") as binary:
                        binary.write(bytes((first,)) + encoded + payload)
                    packet_type = first >> 4
                    if packet_type == 1:
                        log_record(args.transcript, decode_connect(payload))
                        stream.sendall(b"\x20\x02\x00\x00")
                    elif packet_type == 3:
                        record = decode_publish(first, payload)
                        log_record(args.transcript, record)
                        if record["qos"] == 1:
                            stream.sendall(b"\x40\x02" + struct.pack("!H", record["packet_id"]))
                    elif packet_type == 8:
                        record = decode_subscribe(first, payload)
                        log_record(args.transcript, record)
                        subscribed.update(item["topic"] for item in record["topics"])
                        granted = bytes([item["qos"] for item in record["topics"]])
                        stream.sendall(b"\x90" + bytes((2 + len(granted),))
                                       + struct.pack("!H", record["packet_id"]) + granted)
                        if (not probe_sent and args.probe_topic and args.probe_topic in subscribed):
                            probe = (Path(args.probe_payload_file).read_bytes().rstrip(b"\r\n")
                                     if args.probe_payload_file
                                     else bytes.fromhex(args.probe_payload_hex or ""))
                            send_probe(stream, args.probe_topic, probe, 0x7001,
                                       args.transcript, "LAB_PROBE_SENT")
                            probe_sent = True
                            base = time.monotonic()
                            for spec in args.scheduled_probe:
                                delay_text, probe_path = spec.split(":", 1)
                                scheduled.append((base + float(delay_text), probe_path))
                            scheduled.sort()
                    elif packet_type == 4:
                        packet_id = struct.unpack_from("!H", payload, 0)[0]
                        log_record(args.transcript, {"type": "PUBACK", "packet_id": packet_id})
                    elif packet_type == 12:
                        log_record(args.transcript, {"type": "PINGREQ"})
                        stream.sendall(b"\xd0\x00")
                    elif packet_type == 14:
                        log_record(args.transcript, {"type": "DISCONNECT"})
                        break
                    else:
                        log_record(args.transcript, {"type": "PACKET", "mqtt_type": packet_type,
                                                     "flags": first & 0x0F, "length": len(payload)})
        except (EOFError, ConnectionError, ssl.SSLError) as error:
            log_record(args.transcript, {"type": "CONNECTION_END", "detail": str(error)})
        finally:
            raw.close()


if __name__ == "__main__":
    main()
