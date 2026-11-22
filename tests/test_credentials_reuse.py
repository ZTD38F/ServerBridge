from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


SOURCE = Path("install.sh").read_text(encoding="utf-8")
FUNCTION = "load_existing_credentials() {" + SOURCE.split("load_existing_credentials() {", 1)[1].split("\nprompt_credentials() {", 1)[0]


def scenario(managed: bool, symlink: bool, explicit: bool) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as dirname:
        d = Path(dirname)
        (d / "runtime.env").write_text("CONTROL_PLANE_TUNNEL_ID=tunnel_fake_test\n")
        if managed:
            (d / ".serverbridge-managed").touch()
        secret = d / "key-original"
        secret.write_text("sk-dummy-not-a-real-key\n")
        if symlink:
            (d / "control_plane_api_key").symlink_to(secret)
        else:
            (d / "control_plane_api_key").write_text(secret.read_text())
        key = "sk-explicit-not-a-real-key" if explicit else ""
        expected = key or ("sk-dummy-not-a-real-key" if managed and not symlink else "")
        script = (
            "set -Eeuo pipefail\n"
            'CONFIG_DIR="' + str(d) + '"\n'
            'TUNNEL_ID=""\n'
            'RUNTIME_KEY="' + key + '"\n'
            + FUNCTION + "\nload_existing_credentials\n"
            '[[ "$TUNNEL_ID" == tunnel_fake_test ]]\n'
            '[[ "$RUNTIME_KEY" == "' + expected + '" ]]\n'
            'printf "PASS"\n'
        )
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)


def test_reuses_protected_key_without_printing_secret() -> None:
    r = scenario(True, False, False)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "PASS"
    assert "sk-" not in r.stdout


def test_does_not_read_symlink_or_unmanaged_secret() -> None:
    for managed, symlink in [(True, True), (False, False), (False, True)]:
        r = scenario(managed, symlink, False)
        assert r.returncode == 0, r.stderr


def test_explicit_credential_takes_precedence() -> None:
    r = scenario(True, False, True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "PASS"


if __name__ == "__main__":
    test_reuses_protected_key_without_printing_secret()
    test_does_not_read_symlink_or_unmanaged_secret()
    test_explicit_credential_takes_precedence()
    print("Credential reuse regression passed")
