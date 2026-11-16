"""Regression: failed candidate tool negotiation must not orphan its process."""
from __future__ import annotations
import tempfile
from pathlib import Path
from unittest.mock import patch

from serverbridge import update_engine as updater


class FakeProcess:
    pid = 222
    def poll(self):
        return None


def test_candidate_contract_failure() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "old").mkdir()
        (root / "current").symlink_to(root / "old")
        pidfile = root / "backend.pid"
        pidfile.write_text("111\n")
        stopped = []
        states = []
        switches = []
        def fake_tools(base, *_args):
            if base == updater.ROUTER:
                return [{"name": "must_preserve", "inputSchema": {"type": "object"}}]
            return []
        def fake_state(phase, *args, **kwargs):
            states.append((phase, args, kwargs))
        with (
            patch.object(updater, "ROOT", root),
            patch.object(updater, "STATE", root),
            patch.object(updater, "LOCK", root / "lock"),
            patch.object(updater, "BACKEND_PID", pidfile),
            patch.object(updater, "recover"),
            patch.object(updater, "stage_latest", return_value=("b"*40, root / "candidate", "vNEXT")),
            patch.object(updater, "route", return_value=("old", 18771)),
            patch.object(updater, "is_ancestor", return_value=False),
            patch.object(updater, "auth_json", return_value={"live_process_sessions": 0}),
            patch.object(updater, "tools", side_effect=fake_tools),
            patch.object(updater, "start_backend", return_value=FakeProcess()),
            patch.object(updater, "backend_health", return_value=True),
            patch.object(updater, "stop", side_effect=lambda p: stopped.append(p)),
            patch.object(updater, "write_state", side_effect=fake_state),
            patch.object(updater, "set_route", side_effect=lambda *v: switches.append(v)),
        ):
            try:
                updater.main()
            except RuntimeError as exc:
                assert "breaking tool contract" in str(exc), str(exc)
            else:
                raise AssertionError("Breaking tool contract was accepted")
        assert stopped == [222], stopped
        assert switches == [], switches
        assert states[-1][0] == "FAILED_ROLLED_BACK", states
        assert states[-1][1][-1] == "active route unchanged", states


if __name__ == "__main__":
    test_candidate_contract_failure()
    print("Pre-switch cleanup regression passed")
