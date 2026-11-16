"""Regression checks for bounded process-session output and concurrent admission."""
from __future__ import annotations

import sys
import threading
import time
from unittest.mock import patch

from serverbridge import sessions


def _wait_output(sid: str, expected: int, timeout: float = 3.0) -> None:
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        session = sessions.get(sid)
        if len(session.stdout) >= expected and session.proc.poll() is not None:
            return
        time.sleep(0.02)
    raise AssertionError("process output was not collected")


def test_bounded_buffer_cursor() -> None:
    old_limit = sessions.MAX_LINES
    sessions.MAX_LINES = 3
    sid = None
    try:
        code = "for i in range(8): print(i, flush=True)"
        info = sessions.start([sys.executable, "-u", "-c", code], "/", {})
        sid = info["session_id"]
        _wait_output(sid, 3)
        first = sessions.read(sid, max_lines=10)
        assert first["stdout"] == "5\n6\n7", first
        assert first["stdout_dropped_lines"] == 5, first
        assert first["stdout_has_more"] is False, first
        second = sessions.read(sid, max_lines=10)
        assert second["stdout"] == "", second
        assert second["stdout_dropped_lines"] == 0, second
    finally:
        sessions.MAX_LINES = old_limit
        if sid:
            sessions.terminate(sid)
            sessions._sessions.pop(sid, None)


def test_concurrent_max_sessions() -> None:
    real_popen = sessions.subprocess.Popen
    old_max = sessions.MAX_SESSIONS
    sessions.MAX_SESSIONS = 1
    started = threading.Barrier(2)
    ids: list[str] = []
    errors: list[str] = []

    def slow_popen(*args, **kwargs):
        time.sleep(0.08)
        return real_popen(*args, **kwargs)

    def worker() -> None:
        started.wait()
        try:
            v = sessions.start(
                [sys.executable, "-u", "-c", "import time;time.sleep(0.5)"], "/", {}
            )
            ids.append(v["session_id"])
        except RuntimeError as exc:
            errors.append(str(exc))

    try:
        with patch.object(sessions.subprocess, "Popen", side_effect=slow_popen):
            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=3)
            assert all(not thread.is_alive() for thread in threads), "thread deadlock"
        assert len(ids) == 1, (ids, errors)
        assert errors == ["SESSION_LIMIT"], errors
    finally:
        sessions.MAX_SESSIONS = old_max
        for sid in ids:
            sessions.terminate(sid)
            sessions._sessions.pop(sid, None)


if __name__ == "__main__":
    test_bounded_buffer_cursor()
    test_concurrent_max_sessions()
    print("Process-session integrity tests passed")
