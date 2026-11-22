"""Isolated tests for self-maintaining updater assets and rollback."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import tempfile
import unittest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from serverbridge import update_components as uc


def fixture(tmp_path: Path, custom: bool = False):
    rel = tmp_path / "release"
    bin_dir = tmp_path / "bin"
    unit_dir = tmp_path / "systemd"
    config = tmp_path / "config"
    state = tmp_path / "state"
    for d in (rel / "packaging", bin_dir, unit_dir, config, state):
        d.mkdir(parents=True, exist_ok=True)
    (rel / "auto-update.sh").write_text("#!/bin/bash\\n# serverbridge.update_engine\\necho newer\\n")
    (rel / "packaging/serverbridge-update.timer").write_text("OnUnitInactiveSec=30s\\n")
    (rel / "packaging/serverbridge-update.service").write_text("ExecStart=/usr/local/lib/serverbridge/auto-update\\n")
    (unit_dir / "serverbridge-update.timer").write_text("OnCalendar=daily\\n")
    (unit_dir / "serverbridge-update.service").write_text("ExecStart=/usr/local/lib/serverbridge/old-auto-update\\n")
    old = "#!/bin/bash\\n# sonoryx custom wrapper\\n" if custom else "#!/bin/bash\\n# serverbridge.update_engine\\necho old\\n"
    (bin_dir / "auto-update").write_text(old)
    (bin_dir / "auto-update").chmod(0o755)
    return rel, bin_dir, unit_dir, config, state


class FakeSystemCtl:
    def __init__(self, *, enabled: bool = True, fail_restart_once: bool = False):
        self.enabled = enabled
        self.fail_restart_once = fail_restart_once
        self.actions = []

    def __call__(self, args, **kw):
        self.actions.append(tuple(args))
        if tuple(args[:3]) == ("systemctl", "is-enabled", "--quiet"):
            return subprocess.CompletedProcess(args, 0 if self.enabled else 1)
        if tuple(args[:2]) == ("systemctl", "restart") and self.fail_restart_once:
            self.fail_restart_once = False
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0)


def run(tmp_path: Path, *, custom=False, enabled=True, fail_restart=False, hook=False):
    rel, bind, units, cfg, state = fixture(tmp_path, custom=custom)
    if hook:
        wrapper = tmp_path / "custom.py"
        wrapper.write_text("# owner overlay fixture\\n")
        wrapper.chmod(0o600)
        (cfg / "update-wrapper.path").write_text(str(wrapper))
        (cfg / "update-wrapper.path").chmod(0o600)
    fake = FakeSystemCtl(enabled=enabled, fail_restart_once=fail_restart)
    return (rel, bind, units, cfg, state, fake)


def apply(env):
    rel, bind, units, cfg, state, fake = env
    with patch.object(uc.subprocess, "run", fake):
        return uc.reconcile(rel, bin_dir=bind, systemd_dir=units, config_dir=cfg, state_dir=state)


def test_self_upgrade_and_receipt(tmp_path):
    env = run(tmp_path)
    result = apply(env)
    rel, bind, units, cfg, state, fake = env
    assert result["status"] == "VERIFIED" and result["changed"]
    assert (units / "serverbridge-update.timer").read_bytes() == (rel / "packaging/serverbridge-update.timer").read_bytes()
    assert (units / "serverbridge-update.service").read_bytes() == (rel / "packaging/serverbridge-update.service").read_bytes()
    assert (bind / "auto-update").read_bytes() == (rel / "auto-update.sh").read_bytes()
    receipt = json.loads((state / "updater-components.json").read_text())
    assert receipt["paths"][str(bind / "auto-update")] == hashlib.sha256((bind / "auto-update").read_bytes()).hexdigest()
    assert ("systemctl", "restart", "serverbridge-update.timer") in fake.actions
    assert apply(env)["status"] == "CURRENT"


def test_disabled_owner_timer_is_not_reenabled(tmp_path):
    env = run(tmp_path, enabled=False)
    r = apply(env)
    assert r["status"] == "DISABLED_BY_OWNER"
    assert (env[2] / "serverbridge-update.timer").read_text() == "OnCalendar=daily\\n"


def test_custom_overlay_not_destroyed_without_hook(tmp_path):
    env = run(tmp_path, custom=True)
    r = apply(env)
    assert r["status"] == "CUSTOM_LAUNCHER_NEEDS_HOOK"
    assert "sonoryx custom wrapper" in (env[1] / "auto-update").read_text()
    assert (env[2] / "serverbridge-update.timer").read_text() == "OnCalendar=daily\\n"


def test_registered_custom_overlay_can_migrate_to_generic_launcher(tmp_path):
    env = run(tmp_path, custom=True, hook=True)
    r = apply(env)
    assert r["status"] == "VERIFIED"
    assert (env[3] / "update-wrapper.path").is_file()
    assert "serverbridge.update_engine" in (env[1] / "auto-update").read_text()


def test_partial_install_failure_restores_files(tmp_path):
    env = run(tmp_path, fail_restart=True)
    old = [(env[1] / "auto-update").read_bytes(), (env[2] / "serverbridge-update.timer").read_bytes(),
           (env[2] / "serverbridge-update.service").read_bytes()]
    with unittest.TestCase().assertRaises(subprocess.CalledProcessError):
        apply(env)
    assert [(env[1] / "auto-update").read_bytes(), (env[2] / "serverbridge-update.timer").read_bytes(),
            (env[2] / "serverbridge-update.service").read_bytes()] == old
    assert not (env[4] / "updater-components.json").exists()


def test_world_readable_hook_config_rejected(tmp_path):
    env = run(tmp_path, custom=True, hook=True)
    (env[3] / "update-wrapper.path").chmod(0o644)
    with unittest.TestCase().assertRaises(uc.ReconcileError):
        apply(env)


def test_receipt_failure_rolls_back_update_assets(tmp_path):
    env = run(tmp_path)
    old = (env[1] / "auto-update").read_bytes()
    original = uc._replace

    def fail_receipt(path, payload, mode):
        if path.name == "updater-components.json":
            raise OSError("synthetic receipt failure")
        return original(path, payload, mode)

    with patch.object(uc, "_replace", side_effect=fail_receipt):
        with unittest.TestCase().assertRaises(OSError):
            apply(env)
    assert (env[1] / "auto-update").read_bytes() == old


def test_symlink_unit_rejected(tmp_path):
    env = run(tmp_path)
    timer = env[2] / "serverbridge-update.timer"
    timer.unlink()
    timer.symlink_to(env[0] / "packaging/serverbridge-update.timer")
    with unittest.TestCase().assertRaises(uc.ReconcileError):
        apply(env)


if __name__ == "__main__":
    checks = [
        (name, fn) for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]
    for name, fn in checks:
        with tempfile.TemporaryDirectory(prefix="serverbridge-component-test.") as td:
            fn(Path(td))
    print(f"Updater component rollback and reconciliation: {len(checks)} PASS")
