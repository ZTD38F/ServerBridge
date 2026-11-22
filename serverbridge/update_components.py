"""Reconcile the stable updater service and timer after a verified A/B runtime update.

No arbitrary changes on unrecognised/disabled installations. Supports a
locally managed overlay hook without replacing its original source.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

DEFAULT_ROOT = Path("/opt/serverbridge")
DEFAULT_BIN = Path("/usr/local/lib/serverbridge")
DEFAULT_SYSTEMD = Path("/etc/systemd/system")
DEFAULT_CONFIG = Path("/etc/serverbridge")
DEFAULT_STATE = Path("/var/lib/serverbridge")


class ReconcileError(RuntimeError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _replace(path: Path, raw: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.lexists(name):
            os.unlink(name)


def _run_systemctl(*args: str) -> None:
    subprocess.run(("systemctl", *args), check=True, capture_output=True, text=True, timeout=30)


def reconcile(
    release: Path,
    *,
    bin_dir: Path = DEFAULT_BIN,
    systemd_dir: Path = DEFAULT_SYSTEMD,
    config_dir: Path = DEFAULT_CONFIG,
    state_dir: Path = DEFAULT_STATE,
) -> dict[str, object]:
    """Synchronise updater assets while preserving local service identity.

    Invoked only for an already-verified currently committed release. The
    existing timer must be enabled: an administrator's disabled setting is
    never overridden. For legacy custom launchers, the owner must explicitly
    identify the persistent Python overlay wrapper first.
    """
    release = release.resolve(strict=True)
    timer = systemd_dir / "serverbridge-update.timer"
    service = systemd_dir / "serverbridge-update.service"
    launcher = bin_dir / "auto-update"
    hook = config_dir / "update-wrapper.path"
    if not timer.is_file() or not service.is_file() or not launcher.is_file():
        return {"status": "NOT_INSTALLED", "changed": False}
    is_enabled = subprocess.run(
        ("systemctl", "is-enabled", "--quiet", timer.name),
        check=False, capture_output=True, timeout=10,
    )
    if is_enabled.returncode:
        return {"status": "DISABLED_BY_OWNER", "changed": False}

    for path in (timer, service, launcher):
        if path.is_symlink():
            raise ReconcileError(f"Refusing symlink updater component: {path}")

    sources = (
        (release / "packaging/serverbridge-update.timer", timer, 0o644),
        (release / "packaging/serverbridge-update.service", service, 0o644),
        (release / "auto-update.sh", launcher, 0o755),
    )
    for src, _dest, _mode in sources:
        if not src.is_file() or src.is_symlink():
            raise ReconcileError(f"Verified release component missing: {src}")

    current_launcher = launcher.read_text(encoding="utf-8")
    standard_marker = "serverbridge.update_engine"
    if standard_marker not in current_launcher:
        if not hook.is_file() or hook.is_symlink():
            # Cannot replace owner-maintained custom updater without preserving hook.
            return {"status": "CUSTOM_LAUNCHER_NEEDS_HOOK", "changed": False}
        hook_st = hook.stat()
        if hook_st.st_uid != os.geteuid() or hook_st.st_mode & 0o077:
            raise ReconcileError("Update-wrapper configuration must be owner-only")
        target = hook.read_text(encoding="utf-8").strip()
        wrapper = Path(target)
        if not wrapper.is_absolute() or not wrapper.is_file() or wrapper.is_symlink():
            raise ReconcileError("Invalid update-wrapper.path")
        st = wrapper.stat()
        if st.st_uid != os.geteuid() or st.st_mode & 0o022:
            raise ReconcileError("Update hook is not exclusively owner-managed")

    before: dict[Path, tuple[bytes, int]] = {}
    changes: list[tuple[Path, bytes, int]] = []
    for src, dest, mode in sources:
        prior = dest.read_bytes()
        before[dest] = (prior, dest.stat().st_mode & 0o7777)
        candidate = src.read_bytes()
        if prior != candidate or before[dest][1] != mode:
            changes.append((dest, candidate, mode))
    if not changes:
        return {"status": "CURRENT", "changed": False, "version": release.name}

    timer_changed = any(path == timer for path, _buf, _mode in changes)
    touched = []
    try:
        for path, content, mode in changes:
            _replace(path, content, mode)
            touched.append(path)
        _run_systemctl("daemon-reload")
        if timer_changed:
            _run_systemctl("restart", timer.name)
        _run_systemctl("is-active", "--quiet", timer.name)
        for path, contents, mode in changes:
            if path.read_bytes() != contents or (path.stat().st_mode & 0o7777) != mode:
                raise ReconcileError(f"Post-update readback mismatch: {path}")
    except BaseException:
        for path in reversed(touched):
            old, mode = before[path]
            _replace(path, old, mode)
        _run_systemctl("daemon-reload")
        if timer_changed:
            _run_systemctl("restart", timer.name)
        raise

    result: dict[str, object] = {
        "status": "VERIFIED",
        "changed": True,
        "version": release.name,
        "paths": {str(dest): _sha(dest.read_bytes()) for _src, dest, _mode in sources},
        "time": int(time.time()),
    }
    receipt = state_dir / "updater-components.json"
    try:
        _replace(receipt, (json.dumps(result, sort_keys=True) + "\n").encode(), 0o600)
    except BaseException:
        # Never report a verified result without its durable receipt.
        for path in reversed(touched):
            old, mode = before[path]
            _replace(path, old, mode)
        _run_systemctl("daemon-reload")
        if timer_changed:
            _run_systemctl("restart", timer.name)
        raise
    return result
