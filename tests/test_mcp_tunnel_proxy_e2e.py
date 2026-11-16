"""End-to-end MCP initialize, tools/list and tools/call through the real HTTP router.

Runs two authentic Python MCP backends on ephemeral loopback ports. No
production service, real key, tunnel, or server state is modified.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from serverbridge import supervisor


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _backend_health(port: int, token: str) -> bool:
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/healthz",
            headers={"X-Bridge-Backend-Token": token},
        )
        with urllib.request.urlopen(req, timeout=1) as response:
            return json.load(response)["ok"] is True
    except Exception:
        return False


def _rpc(port: int, router_token: str, method: str, params: dict | None = None) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    payload = json.dumps({"jsonrpc": "2.0", "id": 9, "method": method, "params": params or {}})
    try:
        conn.request("POST", "/mcp", body=payload, headers={
            "X-Bridge-Token": router_token,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        })
        response = conn.getresponse()
        return response.status, json.loads(response.read())
    finally:
        conn.close()


def test_live_mcp_router() -> None:
    processes: list[subprocess.Popen] = []
    router: ThreadingHTTPServer | None = None
    router_thread: threading.Thread | None = None
    with tempfile.TemporaryDirectory(prefix="serverbridge-mcp-e2e-") as td:
        token = "B" * 48
        router_token = "R" * 48
        token_path = Path(td) / "backend-token"
        token_path.write_text(token, encoding="utf-8")
        token_path.chmod(0o600)
        ports = [_free_port(), _free_port()]
        assert ports[0] != ports[1]
        env = os.environ.copy()
        env["SERVERBRIDGE_BACKEND_TOKEN_FILE"] = str(token_path)
        env["SERVERBRIDGE_ENABLE_EXEC"] = "0"
        env["SERVERBRIDGE_ENABLE_WRITE"] = "0"
        env["SERVERBRIDGE_ENABLE_PROCESS"] = "0"
        env["SERVERBRIDGE_ENABLE_SERVICE_CONTROL"] = "0"
        env["SERVERBRIDGE_ALLOWED_ROOTS"] = td
        state = {"generation": "previous", "port": ports[0]}
        try:
            for port in ports:
                proc = subprocess.Popen(
                    [sys.executable, "-m", "serverbridge.http_runtime", "--port", str(port)],
                    env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True,
                )
                processes.append(proc)
            deadline = time.monotonic() + 12
            for port, proc in zip(ports, processes):
                while time.monotonic() < deadline and not _backend_health(port, token):
                    if proc.poll() is not None:
                        raise AssertionError(f"MCP backend exited with {proc.returncode}")
                    time.sleep(0.1)
                assert _backend_health(port, token), f"backend {port} unhealthy"
            router = ThreadingHTTPServer(("127.0.0.1", 0), supervisor.H)
            router.daemon_threads = True
            with (
                patch.object(supervisor, "route", side_effect=lambda: (
                    state["generation"], state["port"]
                )),
                patch.object(supervisor, "secret", side_effect=lambda file: (
                    router_token if file == supervisor.ROUTER_TOKEN else token
                )),
            ):
                router_thread = threading.Thread(target=router.serve_forever, daemon=True)
                router_thread.start()
                local_port = router.server_address[1]
                status, _ = _rpc(local_port, "wrong", "tools/list")
                assert status == 403, status
                initialize = {
                    "protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "ServerBridge E2E", "version": "1"},
                }
                status, body = _rpc(local_port, router_token, "initialize", initialize)
                assert status == 200 and "result" in body, (status, body)
                status, body = _rpc(local_port, router_token, "tools/list")
                names = {tool["name"] for tool in body["result"]["tools"]}
                assert status == 200 and "server_info" in names, (status, names)
                assert "run_command" not in names, "mutation tool leaked into read-only runtime"
                status, body = _rpc(local_port, router_token, "tools/call", {
                    "name": "server_info", "arguments": {},
                })
                assert status == 200 and "result" in body, (status, body)
                old_pids = [proc.pid for proc in processes]
                state["generation"], state["port"] = "candidate", ports[1]
                status, body = _rpc(local_port, router_token, "tools/list")
                names_after = {tool["name"] for tool in body["result"]["tools"]}
                assert status == 200 and names_after == names, (status, names_after)
                assert [proc.pid for proc in processes] == old_pids
                assert all(proc.poll() is None for proc in processes)
        finally:
            if router is not None:
                router.shutdown()
                router.server_close()
            if router_thread is not None:
                router_thread.join(timeout=2)
            for proc in processes:
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)


if __name__ == "__main__":
    test_live_mcp_router()
    print("Real MCP router end-to-end passed")
