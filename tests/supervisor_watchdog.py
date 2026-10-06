from __future__ import annotations

from serverbridge import supervisor


def main() -> None:
    calls: list[str] = []
    sleeps = 0

    original_ensure = supervisor.ensure_backend
    original_sleep = supervisor.time.sleep

    def fake_ensure_backend() -> int:
        calls.append("ensure")
        if len(calls) == 1:
            raise RuntimeError("simulated backend outage")
        return 12345

    def fake_sleep(_seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise SystemExit(0)

    supervisor.ensure_backend = fake_ensure_backend
    supervisor.time.sleep = fake_sleep
    try:
        try:
            supervisor.watch_backend(interval=0.0)
        except SystemExit:
            pass
    finally:
        supervisor.ensure_backend = original_ensure
        supervisor.time.sleep = original_sleep

    assert len(calls) >= 2, calls
    assert sleeps >= 2, sleeps
    print("Supervisor watchdog recovery loop passed")


if __name__ == "__main__":
    main()
