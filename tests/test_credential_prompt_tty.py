"""Actual Linux pseudo-TTY integration: real /dev/tty read and hidden API-key entry."""
from __future__ import annotations

import os
import pty
import select
import signal
import tempfile
import time
from pathlib import Path

SOURCE = Path("install.sh").read_text(encoding="utf-8")
FUNCTIONS = (
    "visible_input() {"
    + SOURCE.split("visible_input() {", 1)[1].split("\nselect_access_mode() {", 1)[0]
)


def exercise(saved: bool, replacements: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="serverbridge-tty-test-") as tmp:
        root = Path(tmp)
        if saved:
            (root / "runtime.env").write_text("CONTROL_PLANE_TUNNEL_ID=tunnel_existing1234\n")
            (root / ".serverbridge-managed").touch()
            (root / "control_plane_api_key").write_text("sk-test-saved-key\n")
        shell = """set -Eeuo pipefail
CONFIG_DIR="$MOCK_CONFIG_DIR"
TUNNEL_ID=""
RUNTIME_KEY=""
TUNNEL_ID_EXPLICIT=0
RUNTIME_KEY_EXPLICIT=0
DRY_RUN=0
RESET=""; BOLD=""; DIM=""; BLUE=""
say() { printf '%s\\n' "$*"; }
info() { printf 'INFO %s\\n' "$*"; }
ok() { printf 'OK %s\\n' "$*"; }
die() { printf 'FAIL %s\\n' "$*" >&2; exit 6; }
""" + FUNCTIONS + """
load_existing_credentials
prompt_credentials
[[ "$TUNNEL_ID" == "$EXPECTED_ID" ]]
[[ "$RUNTIME_KEY" == "$EXPECTED_KEY" ]]
echo "E2E_OK"
"""
        script = root / "simulate.sh"
        script.write_text(shell)
        env = os.environ.copy()
        env.update({
            "MOCK_CONFIG_DIR": str(root),
            "EXPECTED_ID": "tunnel_new98765" if replacements or not saved else "tunnel_existing1234",
            "EXPECTED_KEY": "sk-test-new-key" if replacements or not saved else "sk-test-saved-key",
        })
        steps = (
            [("Reuse previously saved Tunnel ID? [Y/n]:", "n\n"),
             ("New Tunnel ID:", "tunnel_new98765\n"),
             ("Reuse previously saved runtime API key? [Y/n]:", "n\n"),
             ("New runtime API key:", "sk-test-new-key\n")]
            if replacements and saved else
            [("Reuse previously saved Tunnel ID? [Y/n]:", "\n"),
             ("Reuse previously saved runtime API key? [Y/n]:", "\n")]
            if saved else
            [("New Tunnel ID:", "tunnel_new98765\n"),
             ("New runtime API key:", "sk-test-new-key\n")]
        )
        child, fd = pty.fork()
        if child == 0:
            os.execvpe("bash", ["bash", str(script)], env)
        raw = b""
        pending = 0
        deadline = time.monotonic() + 12
        try:
            while time.monotonic() < deadline:
                ready, _, _ = select.select([fd], [], [], 0.2)
                if ready:
                    try:
                        chunk = os.read(fd, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    raw += chunk
                while pending < len(steps) and steps[pending][0].encode() in raw:
                    os.write(fd, steps[pending][1].encode())
                    pending += 1
                if b"E2E_OK" in raw:
                    break
            text = raw.decode("utf-8", "replace")
            assert pending == len(steps), f"Missing expected prompts: {text[-900:]}"
            assert "E2E_OK" in text, f"TTY interaction failed: {text[-900:]}"
            assert "sk-test-" not in text, "Secret leaked in terminal transcript"
        finally:
            try:
                os.kill(child, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(child, 0)
            except ChildProcessError:
                pass
            os.close(fd)


if __name__ == "__main__":
    exercise(saved=True, replacements=False)
    exercise(saved=True, replacements=True)
    exercise(saved=False, replacements=False)
    print("PTY /dev/tty install prompts passed (saved, replaced, new)")
