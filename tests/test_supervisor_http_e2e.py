"""Real loopback HTTP E2E: authentication, routing and in-flight drain."""
from __future__ import annotations

import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from serverbridge import supervisor


def test_http_router() -> None:
    first_started = threading.Event()
    finish_first = threading.Event()
    state = {"active": "one", "port": 0}
    servers = []
    threads = []

    def make_backend(label: str):
        class Backend(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                return

            def do_POST(self):
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(n) or b"{}")
                if label == "one" and body.get("method") == "slow":
                    first_started.set()
                    assert finish_first.wait(3), "timed out waiting for drain"
                payload = json.dumps({
                    "jsonrpc": "2.0", "id": body.get("id", 1),
                    "result": {"backend": label}
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        instance = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        instance.daemon_threads = True
        servers.append(instance)
        return instance.server_address[1]

    def request(port: int, method: str, token: str):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
        data = json.dumps({"jsonrpc": "2.0", "id": 5, "method": method})
        try:
            conn.request("POST", "/mcp", body=data, headers={
                "X-Bridge-Token": token,
                "Content-Type": "application/json",
            })
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    try:
        first = make_backend("one")
        second = make_backend("two")
        state["port"] = first
        router = ThreadingHTTPServer(("127.0.0.1", 0), supervisor.H)
        router.daemon_threads = True
        servers.append(router)
        with (
            patch.object(supervisor, "route", side_effect=lambda: (state["active"], state["port"])),
            patch.object(supervisor, "secret", side_effect=lambda path: (
                "A"*32 if path == supervisor.ROUTER_TOKEN else "B"*32
            )),
        ):
            for srv in servers:
                t = threading.Thread(target=srv.serve_forever, daemon=True)
                t.start()
                threads.append(t)
            port = router.server_address[1]
            status, _ = request(port, "tools/list", "bad-token")
            assert status == 403, status
            status, body = request(port, "tools/list", "A"*32)
            assert status == 200 and body["result"]["backend"] == "one", (status, body)
            slow = []
            t = threading.Thread(
                target=lambda: slow.append(request(port, "slow", "A"*32)),
                daemon=True,
            )
            t.start()
            assert first_started.wait(2), "first request never reached old backend"
            assert supervisor.INFLIGHT.get("one", 0) >= 1
            state["active"], state["port"] = "two", second
            status, body = request(port, "tools/list", "A"*32)
            assert status == 200 and body["result"]["backend"] == "two", (status, body)
            finish_first.set()
            t.join(timeout=3)
            assert not t.is_alive() and slow, "old request did not drain"
            assert slow[0][1]["result"]["backend"] == "one", slow
            assert supervisor.INFLIGHT.get("one", 0) == 0
    finally:
        finish_first.set()
        for srv in servers:
            srv.shutdown()
            srv.server_close()
        for t in threads:
            t.join(timeout=1)


if __name__ == "__main__":
    test_http_router()
    print("Supervisor HTTP end-to-end passed")
