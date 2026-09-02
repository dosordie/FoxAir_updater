#!/usr/bin/env python3
"""Loopback-only LinkedGo credential endpoint with synthetic lab values."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


RESPONSE = {
    "error_code": 0,
    "object_result": {
        "device_code": "LABDEVICE001",
        "product_key": "a1LABTEST01",
        "device_secret": "0123456789abcdef0123456789abcdef",
    },
}


class Handler(BaseHTTPRequestHandler):
    server_version = "PHNIXLab/1"

    def _reply(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        record = {
            "method": self.command,
            "path": self.path,
            "body": body.decode("utf-8", "replace"),
        }
        with open(self.server.transcript, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        payload = json.dumps(RESPONSE, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _reply
    do_POST = _reply

    def log_message(self, _format, *_args):
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript", required=True)
    args = parser.parse_args()
    server = HTTPServer(("127.0.0.1", 84), Handler)
    server.transcript = args.transcript
    server.serve_forever()


if __name__ == "__main__":
    main()
