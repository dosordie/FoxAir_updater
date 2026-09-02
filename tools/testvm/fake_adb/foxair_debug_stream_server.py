#!/usr/bin/env python3
"""Expose the current phnixIot4G ttyGS0 capture as a raw TCP stream."""

import argparse
import asyncio
import contextlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path


LOG = logging.getLogger("foxair-debug-stream")


def stream_enabled(state_file: Path) -> bool:
    """Return the persistent debug-stream mode; missing/invalid means enabled."""
    try:
        return state_file.read_text(encoding="ascii").strip().lower() != "off"
    except OSError:
        return True


def newest_capture(logs_root: Path) -> Path | None:
    candidates = list(logs_root.glob("*/ttyGS0-from-app.bin"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, str(path)))


@dataclass
class CaptureFollower:
    logs_root: Path
    path: Path | None = None
    offset: int = 0
    initialized: bool = False

    def poll(self) -> bytes:
        candidate = newest_capture(self.logs_root)
        if candidate is None:
            return b""
        if candidate != self.path:
            self.path = candidate
            size = candidate.stat().st_size
            # A newly connected client only receives live data. If the runner
            # rotates to a new capture, its startup output is included.
            self.offset = size if not self.initialized else 0
            self.initialized = True
        size = self.path.stat().st_size
        if size < self.offset:
            self.offset = 0
        if size == self.offset:
            return b""
        with self.path.open("rb") as capture:
            capture.seek(self.offset)
            data = capture.read(min(size - self.offset, 65536))
        self.offset += len(data)
        return data


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    logs_root: Path,
    state_file: Path,
) -> None:
    peer = writer.get_extra_info("peername")
    LOG.info("client connected: %s", peer)
    follower = CaptureFollower(logs_root)
    was_enabled = False
    disconnect = asyncio.create_task(reader.read(1))
    try:
        while not disconnect.done():
            enabled = stream_enabled(state_file)
            if not enabled:
                # Keep TCP 5039 reachable, but discard the current capture so
                # enabling later never replays bytes produced while muted.
                follower = CaptureFollower(logs_root)
                was_enabled = False
                await asyncio.sleep(0.1)
                continue
            if not was_enabled:
                follower = CaptureFollower(logs_root)
                follower.poll()  # establish live EOF without replay
                was_enabled = True
                data = b""
            else:
                data = follower.poll()
            if data:
                writer.write(data)
                await writer.drain()
            else:
                await asyncio.sleep(0.1)
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        disconnect.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await disconnect
        writer.close()
        await writer.wait_closed()
        LOG.info("client disconnected: %s", peer)


async def serve(bind: str, port: int, logs_root: Path, state_file: Path) -> None:
    server = await asyncio.start_server(
        lambda reader, writer: handle_client(reader, writer, logs_root, state_file), bind, port
    )
    sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    LOG.info(
        "serving raw ttyGS0 debug stream on %s; captures=%s; state=%s",
        sockets,
        logs_root,
        state_file,
    )
    async with server:
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default=os.environ.get("FOXAIR_DEBUG_BIND", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("FOXAIR_DEBUG_PORT", "5039")))
    parser.add_argument(
        "--logs-root",
        default=os.environ.get("FOXAIR_DEBUG_LOGS_ROOT", "/opt/phnix-lab/logs"),
    )
    parser.add_argument(
        "--state-file",
        default=os.environ.get(
            "FOXAIR_DEBUG_STREAM_STATE",
            "/var/lib/foxair-fake-adb/debug-stream.state",
        ),
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(serve(args.bind, args.port, Path(args.logs_root), Path(args.state_file)))


if __name__ == "__main__":
    main()
