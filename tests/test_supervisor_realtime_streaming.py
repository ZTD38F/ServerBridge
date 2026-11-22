"""End-to-end incremental HTTP event-stream delivery through the authenticated router.

The first SSE frame must reach the caller before the backend sends the final
frame. A large blocking upstream read makes this assertion fail.
"""
from __future__ import annotations

import http.client
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from serverbridge import supervisor

FIRST = b"data: first\n\n"
SECOND = b"data: second\n\n"

def test_sse_first_frame_is_realtime() -> None:
    sent = threading.Event()
    finish = threading.Event()
    received = threading.Event()
    router: ThreadingHTTPServer | None = None
    backend: ThreadingHTTPServer | None = None
    threads: list[threading.Thread] = []
    errors: list[str] = []

    class StreamingBackend(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            return

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            first_chunk = f"{len(FIRST):X}\r\n".encode() + FIRST + b"\r\n"
            self.wfile.write(first_chunk)
            self.wfile.flush()
            sent.set()
            if not finish.wait(4):
                errors.append("backend timeout before completion")
                return
            last_chunk = f"{len(SECOND):X}\r\n".encode() + SECOND + b"\r\n0\r\n\r\n"
            try:
                self.wfile.write(last_chunk)
                self.wfile.flush()
            except BrokenPipeError:
                pass

    def run_client(port: int):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", "/mcp", headers={"X-Bridge-Token": "R"*48})
            response = connection.getresponse()
            if response.status != 200:
                errors.append(f"bad response status: {response.status}")
                return
            frame = response.read(len(FIRST))
            if frame != FIRST:
                errors.append(f"unexpected first frame: {frame!r}")
                return
            received.set()
            second = response.read(len(SECOND))
            if second != SECOND:
                errors.append(f"unexpected second frame: {second!r}")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            connection.close()

    try:
        backend = ThreadingHTTPServer(("127.0.0.1", 0), StreamingBackend)
        backend.daemon_threads = True
        router = ThreadingHTTPServer(("127.0.0.1", 0), supervisor.H)
        router.daemon_threads = True
        with (
            patch.object(supervisor, "route", return_value=("stream", backend.server_address[1])),
            patch.object(supervisor, "secret", side_effect=lambda path: (
                "R"*48 if path == supervisor.ROUTER_TOKEN else "B"*48
            )),
        ):
            for server in (backend, router):
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                threads.append(thread)
            client = threading.Thread(target=run_client, args=(router.server_address[1],), daemon=True)
            client.start()
            assert sent.wait(2), "backend did not flush first SSE frame"
            # Check early delivery BEFORE completing the backend response.
            delivered_early = received.wait(0.7)
            finish.set()
            client.join(timeout=4)
            assert not client.is_alive(), "streaming client stalled"
            assert not errors, errors
            assert delivered_early, "router buffered first SSE frame until response completion"
    finally:
        finish.set()
        for server in (router, backend):
            if server:
                server.shutdown()
                server.server_close()
        for thread in threads:
            thread.join(timeout=2)


if __name__ == "__main__":
    test_sse_first_frame_is_realtime()
    print("HTTP SSE real-time delivery E2E passed")
