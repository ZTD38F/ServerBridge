from __future__ import annotations

import hashlib
import os
import platform
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

mcp = MCPServer("ServerBridge")

MAX_CAPTURE = int(os.getenv("SERVERBRIDGE_MAX_CAPTURE_BYTES", "65536"))


def _allowed_roots() -> list[Path]:
    raw = os.getenv("SERVERBRIDGE_ALLOWED_ROOTS", "/")
    roots = [Path(x.strip()).expanduser().resolve() for x in raw.split(":") if x.strip()]
    return roots or [Path("/")]


def _resolve_allowed(path: str) -> Path:
    resolved = Path(path).expanduser().resolve(strict=True)
    for root in _allowed_roots():
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise PermissionError(f"Path is outside SERVERBRIDGE_ALLOWED_ROOTS: {resolved}")


def _truncate(data: str) -> tuple[str, bool]:
    encoded = data.encode("utf-8", errors="replace")
    if len(encoded) <= MAX_CAPTURE:
        return data, False
    return encoded[:MAX_CAPTURE].decode("utf-8", errors="replace") + "\n…[truncated]", True


@mcp.tool()
def server_info() -> dict[str, Any]:
    """Return a concise non-secret snapshot of the server."""
    usage = shutil.disk_usage("/")
    try:
        uptime = float(Path("/proc/uptime").read_text().split()[0])
    except Exception:
        uptime = None
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "cwd": os.getcwd(),
        "uptime_seconds": uptime,
        "disk_root": {"total": usage.total, "used": usage.used, "free": usage.free},
        "allowed_roots": [str(p) for p in _allowed_roots()],
    }


@mcp.tool()
def list_files(path: str = ".", limit: int = 200, include_hidden: bool = True) -> dict[str, Any]:
    """List one directory within SERVERBRIDGE_ALLOWED_ROOTS."""
    target = _resolve_allowed(path)
    if not target.is_dir():
        raise NotADirectoryError(str(target))
    limit = max(1, min(int(limit), 2000))
    entries = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if not include_hidden and child.name.startswith("."):
            continue
        try:
            st = child.lstat()
            entries.append({
                "name": child.name,
                "path": str(child),
                "type": "symlink" if child.is_symlink() else "dir" if child.is_dir() else "file",
                "size": st.st_size,
                "mode": oct(st.st_mode & 0o7777),
                "mtime": int(st.st_mtime),
            })
        except OSError as exc:
            entries.append({"name": child.name, "path": str(child), "error": str(exc)})
        if len(entries) >= limit:
            break
    return {"path": str(target), "entries": entries}


@mcp.tool()
def read_text(path: str, max_bytes: int = 131072) -> dict[str, Any]:
    """Read a UTF-8 text file with a bounded response."""
    target = _resolve_allowed(path)
    if not target.is_file():
        raise FileNotFoundError(str(target))
    cap = max(1, min(int(max_bytes), 4 * 1024 * 1024))
    data = target.read_bytes()
    return {
        "path": str(target),
        "text": data[:cap].decode("utf-8", errors="replace"),
        "truncated": len(data) > cap,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _service_name(name: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@_.:-")
    if not name or len(name) > 200 or any(ch not in allowed for ch in name):
        raise ValueError("Invalid service name")
    return name


@mcp.tool()
def service_status(name: str) -> dict[str, Any]:
    """Read systemd service state and recent status."""
    if shutil.which("systemctl") is None:
        raise RuntimeError("systemctl is not available")
    name = _service_name(name)
    active = subprocess.run(["systemctl", "is-active", name], text=True, capture_output=True, check=False)
    enabled = subprocess.run(["systemctl", "is-enabled", name], text=True, capture_output=True, check=False)
    detail = subprocess.run(
        ["systemctl", "status", name, "--no-pager", "--lines=30"],
        text=True,
        capture_output=True,
        check=False,
    )
    text, truncated = _truncate((detail.stdout or "") + (detail.stderr or ""))
    return {
        "service": name,
        "active": (active.stdout or active.stderr).strip(),
        "enabled": (enabled.stdout or enabled.stderr).strip(),
        "status": text,
        "truncated": truncated,
    }


@mcp.tool()
def service_logs(name: str, lines: int = 100) -> dict[str, Any]:
    """Read recent journal entries for one systemd service."""
    if shutil.which("journalctl") is None:
        raise RuntimeError("journalctl is not available")
    name = _service_name(name)
    lines = max(1, min(int(lines), 2000))
    proc = subprocess.run(
        ["journalctl", "-u", name, "-n", str(lines), "--no-pager", "--output=short-iso"],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    out, truncated = _truncate((proc.stdout or "") + (proc.stderr or ""))
    return {"service": name, "exit_code": proc.returncode, "output": out, "truncated": truncated}


@mcp.tool()
def process_list(limit: int = 200) -> dict[str, Any]:
    """List running processes without exposing process environment variables."""
    limit = max(1, min(int(limit), 2000))
    proc = subprocess.run(
        ["ps", "-eo", "pid,ppid,user,stat,lstart,%cpu,%mem,comm", "--sort=-%cpu"],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    lines = (proc.stdout or "").splitlines()
    selected = lines[: limit + 1]
    out, truncated = _truncate("\n".join(selected))
    return {
        "exit_code": proc.returncode,
        "output": out,
        "truncated": truncated or len(lines) > len(selected),
    }


if __name__ == "__main__":
    mcp.run()
