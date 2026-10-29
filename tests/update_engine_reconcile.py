from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from serverbridge import update_engine


def test_transport_version_normalization() -> None:
    assert update_engine.normalize_transport_version(
        "0.0.15+a390c168ff1b2d14 (git sha: a390c)"
    ) == "v0.0.15"
    assert update_engine.normalize_transport_version("v0.0.15") == "v0.0.15"
    assert update_engine.normalize_transport_version("") == ""


def test_supervisor_generation_marker() -> None:
    with tempfile.TemporaryDirectory() as td:
        marker = Path(td) / "supervisor-generation"
        old_marker = update_engine.SUPERVISOR_GENERATION
        old_auth = update_engine.auth_json
        old_run = update_engine.subprocess.run
        calls: list[object] = []

        def fake_auth(url, *_args, **_kwargs):
            if url.endswith("/__bridge/status"):
                return {"inflight": {}}
            return {"ok": True}

        def fake_run(*args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(returncode=0)

        update_engine.SUPERVISOR_GENERATION = marker
        update_engine.auth_json = fake_auth
        update_engine.subprocess.run = fake_run
        try:
            candidate = SimpleNamespace(name="generation-test")
            assert update_engine.update_supervisor(candidate) is True
            assert marker.read_text().strip() == "generation-test"
            assert len(calls) == 1

            assert update_engine.update_supervisor(candidate) is True
            assert len(calls) == 1
        finally:
            update_engine.SUPERVISOR_GENERATION = old_marker
            update_engine.auth_json = old_auth
            update_engine.subprocess.run = old_run



def test_pid_liveness_rejects_unreaped_zombie() -> None:
    """Linux /proc is authoritative: kill(pid, 0) also succeeds for zombies."""
    import os
    import time
    from serverbridge import supervisor

    for module in (update_engine, supervisor):
        assert module.alive(os.getpid()) is True
        assert module.alive(0) is False
        assert module.alive(-1) is False
        assert module.alive(99999999) is False

    pid = os.fork()
    if pid == 0:
        os._exit(0)
    try:
        for _ in range(200):
            raw = Path(f"/proc/{pid}/stat").read_text()
            if raw.rsplit(")", 1)[1].split()[0] == "Z":
                break
            time.sleep(0.01)
        else:
            raise AssertionError("fixture child never entered zombie state")
        os.kill(pid, 0)
        assert update_engine.alive(pid) is False
        assert supervisor.alive(pid) is False
    finally:
        os.waitpid(pid, 0)

def main() -> None:
    test_transport_version_normalization()
    test_supervisor_generation_marker()
    test_pid_liveness_rejects_unreaped_zombie()
    print("Updater reconciliation tests passed")


if __name__ == "__main__":
    main()
