from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


INSTALLER = Path("install.sh").read_text(encoding="utf-8")
FUNCTION = "select_access_mode() {" + INSTALLER.split("select_access_mode() {", 1)[1].split("\nOS_ID=", 1)[0]


def run_select(mode: str | None, legacy: str | None, previous: str | None) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as directory:
        cfg = Path(directory)
        if previous is not None:
            (cfg / "serverbridge.env").write_text("SERVERBRIDGE_ENABLE_EXEC=" + previous + "\n")
        env = os.environ.copy()
        env.pop("SERVERBRIDGE_ENABLE_EXEC", None)
        env.pop("SERVERBRIDGE_ACCESS_MODE", None)
        if legacy is not None:
            env["SERVERBRIDGE_ENABLE_EXEC"] = legacy
        if mode is not None:
            env["SERVERBRIDGE_ACCESS_MODE"] = mode
        script = (
            'set -Eeuo pipefail\n'
            'ACCESS_MODE="$(printenv SERVERBRIDGE_ACCESS_MODE || true)"\n'
            'DRY_RUN=1\n'
            'CONFIG_DIR="' + str(cfg) + '"\n'
            'warn() { :; }\n'
            'info() { :; }\n'
            'die() { printf "%s\\n" "$*" >&2; exit 2; }\n'
            + FUNCTION + '\nselect_access_mode\nprintf "%s" "$ACCESS_MODE"\n'
        )
        return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, check=False)


def test_explicit_admin_readonly_and_invalid_modes() -> None:
    assert run_select("full", None, "0").stdout == "full"
    assert run_select("readonly", None, "1").stdout == "readonly"
    assert run_select("invalid", None, None).returncode != 0


def test_unattended_preserves_mode_without_silent_privilege_escalation() -> None:
    assert run_select(None, None, None).stdout == "readonly"
    assert run_select(None, None, "0").stdout == "readonly"
    assert run_select(None, None, "1").stdout == "full"


def test_legacy_env_mode() -> None:
    assert run_select(None, "1", "0").stdout == "full"
    assert run_select(None, "0", "1").stdout == "readonly"


def test_installer_writes_and_verifies_all_four_capabilities() -> None:
    for suffix in ("EXEC", "WRITE", "PROCESS", "SERVICE_CONTROL"):
        assert "SERVERBRIDGE_ENABLE_" + suffix + "=$exec_enabled" in INSTALLER
    assert "verify_access_flags" in INSTALLER
    assert "--full-access)" in INSTALLER
    assert "--read-only)" in INSTALLER
    assert "SERVERBRIDGE_PROTECTED_PATHS=" in INSTALLER


if __name__ == "__main__":
    test_explicit_admin_readonly_and_invalid_modes()
    test_unattended_preserves_mode_without_silent_privilege_escalation()
    test_legacy_env_mode()
    test_installer_writes_and_verifies_all_four_capabilities()
    print("Full-access installer contract tests passed")
