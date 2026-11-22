"""Real one-command piped bootstrap PTY regression using the actual stable bootstrap.

Synthetic fake curl/sudo executables: no network, credentials, root, or
installed service files are touched.
"""
from __future__ import annotations

import os
import pty
import select
import signal
import tempfile
import time
from pathlib import Path

from test_credential_prompt_tty import FUNCTIONS

BOOTSTRAP = Path("bootstrap.sh").resolve()
URL = "https://github.com/ZTD38F/ServerBridge/releases/latest/download/bootstrap.sh"


def exercise(*, saved: bool, replace: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="serverbridge-pipe-tty-") as tmp:
        root = Path(tmp)
        bindir = root / "bin"
        bindir.mkdir()
        config = root / "config"
        config.mkdir()
        if saved:
            (config / "runtime.env").write_text("CONTROL_PLANE_TUNNEL_ID=tunnel_saved12345\n")
            (config / ".serverbridge-managed").touch()
            (config / "control_plane_api_key").write_text("sk-test-saved-synthetic\n")

        payload = root / "fixture-install.sh"
        script = r'''#!/usr/bin/env bash
set -Eeuo pipefail
CONFIG_DIR="$MOCK_CONFIG_DIR"
TUNNEL_ID=""
RUNTIME_KEY=""
TUNNEL_ID_EXPLICIT=0
RUNTIME_KEY_EXPLICIT=0
DRY_RUN=0
RESET=""; BOLD=""; DIM=""; BLUE=""
say() { printf '%s\n' "$*"; }
info() { printf 'INFO %s\n' "$*"; }
ok() { printf 'OK %s\n' "$*"; }
die() { printf 'FAIL %s\n' "$*" >&2; exit 7; }
''' + FUNCTIONS + r'''
tty_state_before="$(stty -g </dev/tty)"
load_existing_credentials
prompt_credentials
tty_state_after="$(stty -g </dev/tty)"
[[ "$tty_state_before" == "$tty_state_after" ]]
[[ "$TUNNEL_ID" == "$EXPECTED_TUNNEL" ]]
[[ "$RUNTIME_KEY" == "$EXPECTED_KEY" ]]
printf '%s\n' "ONE_LINE_E2E_OK"
'''
        payload.write_text(script)
        curl = bindir / "curl"
        curl.write_text(r'''#!/usr/bin/env bash
set -Eeuo pipefail
out=""
url=""
while (($#)); do
    case "$1" in
        -o|--output) shift; out="$1";;
        http://*|https://*) url="$1";;
    esac
    shift
done
case "$url" in
    *releases/latest/download/bootstrap.sh) cat "$MOCK_BOOTSTRAP";;
    *api.github.com/repos/ZTD38F/ServerBridge/releases/latest)
        printf '%s\n' '{"tag_name":"v0.5.16"}';;
    *api.github.com/repos/ZTD38F/ServerBridge/commits/v0.5.16)
        printf '%s\n' '{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}';;
    *raw.githubusercontent.com/ZTD38F/ServerBridge/*/install.sh)
        cp "$MOCK_INSTALL" "$out";;
    *) echo "unexpected synthetic curl URL" >&2; exit 7;;
esac
''')
        sudo = bindir / "sudo"
        sudo.write_text("#!/usr/bin/env bash\nexec \"$@\"\n")
        curl.chmod(0o755)
        sudo.chmod(0o755)

        env = os.environ.copy()
        env.update({
            "MOCK_BOOTSTRAP": str(BOOTSTRAP),
            "MOCK_INSTALL": str(payload),
            "MOCK_CONFIG_DIR": str(config),
            "EXPECTED_TUNNEL": "tunnel_replaced98765" if replace or not saved else "tunnel_saved12345",
            "EXPECTED_KEY": "sk-test-replaced-synthetic" if replace or not saved else "sk-test-saved-synthetic",
            "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
            "TMPDIR": str(root),
        })
        prompts = (
            [("Reuse previously saved Tunnel ID? [Y/n]:", "n\n"),
             ("New Tunnel ID:", "tunnel_replaced98765\n"),
             ("Reuse previously saved runtime API key? [Y/n]:", "n\n"),
             ("New runtime API key:", "sk-test-replaced-synthetic\n")]
            if saved and replace else
            [("Reuse previously saved Tunnel ID? [Y/n]:", "\n"),
             ("Reuse previously saved runtime API key? [Y/n]:", "\n")]
            if saved else
            [("New Tunnel ID:", "tunnel_replaced98765\n"),
             ("New runtime API key:", "sk-test-replaced-synthetic\n")]
        )
        pid, fd = pty.fork()
        if pid == 0:
            os.execvpe("bash", ["bash", "-c", f"curl -fsSL {URL} | sudo bash"], env)
        output = b""
        pending = 0
        timeout = time.monotonic() + 15
        try:
            while time.monotonic() < timeout:
                ready, _, _ = select.select([fd], [], [], 0.1)
                if ready:
                    try:
                        buf = os.read(fd, 65536)
                    except OSError:
                        break
                    if not buf:
                        break
                    output += buf
                while pending < len(prompts) and prompts[pending][0].encode() in output:
                    os.write(fd, prompts[pending][1].encode())
                    pending += 1
                if b"ONE_LINE_E2E_OK" in output:
                    break
            assert pending == len(prompts), f"missing prompts: {output[-700:]!r}"
            assert b"ONE_LINE_E2E_OK" in output, f"one-line bootstrap failed: {output[-700:]!r}"
            assert b"sk-test-" not in output, "runtime key echoed into terminal output"
        finally:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            os.waitpid(pid, 0)
            os.close(fd)


if __name__ == "__main__":
    exercise(saved=True, replace=False)
    exercise(saved=True, replace=True)
    exercise(saved=False, replace=False)
    print("True one-command piped bootstrap PTY E2E passed (Enter, replace, fresh)")
