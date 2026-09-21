from __future__ import annotations

import hashlib
import itertools
import os
import platform
import pwd
import shutil
import socket
import subprocess
from collections import deque
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from . import __version__

mcp = MCPServer("ServerBridge")

MAX_CAPTURE = int(os.getenv("SERVERBRIDGE_MAX_CAPTURE_BYTES", "65536"))
MAX_HASH_BYTES = int(os.getenv("SERVERBRIDGE_MAX_HASH_BYTES", str(64 * 1024 * 1024)))


def _allowed_roots() -> list[Path]:
    raw = os.getenv("SERVERBRIDGE_ALLOWED_ROOTS", "/")
    roots = [Path(x.strip()).expanduser().resolve(strict=False) for x in raw.split(":") if x.strip()]
    return roots or [Path("/")]


def _protected_paths() -> list[Path]:
    raw = os.getenv(
        "SERVERBRIDGE_PROTECTED_PATHS",
        "/etc/serverbridge/runtime.env:/etc/serverbridge/network.env:/etc/serverbridge/tunnel-client",
    )
    return [Path(x.strip()).expanduser().resolve(strict=False) for x in raw.split(":") if x.strip()]


def _resolve_allowed(path: str) -> Path:
    resolved = Path(path).expanduser().resolve(strict=True)

    for protected in _protected_paths():
        try:
            resolved.relative_to(protected)
            raise PermissionError(f"Path is protected from MCP file tools: {resolved}")
        except ValueError:
            pass

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


def _sha256_stream(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _init_system() -> str:
    if Path("/run/systemd/system").is_dir() and shutil.which("systemctl"):
        return "systemd"
    if shutil.which("rc-service"):
        return "openrc"
    return "unknown"


@mcp.tool()
def server_info() -> dict[str, Any]:
    """Return a concise non-secret snapshot of the server."""
    usage = shutil.disk_usage("/")
    try:
        uptime = float(Path("/proc/uptime").read_text().split()[0])
    except Exception:
        uptime = None

    return {
        "serverbridge_version": __version__,
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "init_system": _init_system(),
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
    entries: list[dict[str, Any]] = []

    with os.scandir(target) as scan:
        candidates = list(itertools.islice(scan, limit + 1))

    truncated = len(candidates) > limit
    candidates = candidates[:limit]
    candidates.sort(key=lambda entry: entry.name.lower())

    for entry in candidates:
        child = target / entry.name
        try:
            st = entry.stat(follow_symlinks=False)
            kind = (
                "symlink"
                if entry.is_symlink()
                else "dir"
                if entry.is_dir(follow_symlinks=False)
                else "file"
                if entry.is_file(follow_symlinks=False)
                else "other"
            )
            entries.append(
                {
                    "name": entry.name,
                    "path": str(child),
                    "type": kind,
                    "size": st.st_size,
                    "mode": oct(st.st_mode & 0o7777),
                    "mtime": int(st.st_mtime),
                }
            )
        except OSError as exc:
            entries.append({"name": entry.name, "path": str(child), "error": str(exc)})

    return {"path": str(target), "entries": entries, "truncated": truncated}


@mcp.tool()
def read_text(path: str, max_bytes: int = 131072) -> dict[str, Any]:
    """Read a bounded UTF-8 prefix of a regular file."""
    target = _resolve_allowed(path)
    if not target.is_file():
        raise FileNotFoundError(str(target))

    cap = max(1, min(int(max_bytes), 4 * 1024 * 1024))
    size = target.stat().st_size

    with target.open("rb") as handle:
        data = handle.read(cap + 1)

    truncated = len(data) > cap or size > cap
    visible = data[:cap]

    sha256: str | None = None
    if size <= MAX_HASH_BYTES:
        sha256 = _sha256_stream(target)

    return {
        "path": str(target),
        "text": visible.decode("utf-8", errors="replace"),
        "truncated": truncated,
        "size": size,
        "sha256": sha256,
        "sha256_skipped": sha256 is None,
    }


def _service_name(name: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@_.:-")
    if not name or len(name) > 200 or any(ch not in allowed for ch in name):
        raise ValueError("Invalid service name")
    return name


@mcp.tool()
def service_status(name: str) -> dict[str, Any]:
    """Read service state using systemd or OpenRC."""
    name = _service_name(name)
    init = _init_system()

    if init == "systemd":
        active = subprocess.run(
            ["systemctl", "is-active", name],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        enabled = subprocess.run(
            ["systemctl", "is-enabled", name],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        detail = subprocess.run(
            ["systemctl", "status", name, "--no-pager", "--lines=30"],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        text, truncated = _truncate((detail.stdout or "") + (detail.stderr or ""))
        return {
            "service": name,
            "backend": "systemd",
            "active": (active.stdout or active.stderr).strip(),
            "enabled": (enabled.stdout or enabled.stderr).strip(),
            "status": text,
            "truncated": truncated,
        }

    if init == "openrc":
        detail = subprocess.run(
            ["rc-service", name, "status"],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        text, truncated = _truncate((detail.stdout or "") + (detail.stderr or ""))
        return {
            "service": name,
            "backend": "openrc",
            "exit_code": detail.returncode,
            "status": text,
            "truncated": truncated,
        }

    raise RuntimeError("No supported service manager is available")


@mcp.tool()
def service_logs(name: str, lines: int = 100) -> dict[str, Any]:
    """Read recent service logs when a supported log backend is available."""
    name = _service_name(name)
    lines = max(1, min(int(lines), 2000))

    if _init_system() == "systemd" and shutil.which("journalctl"):
        proc = subprocess.run(
            ["journalctl", "-u", name, "-n", str(lines), "--no-pager", "--output=short-iso"],
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        out, truncated = _truncate((proc.stdout or "") + (proc.stderr or ""))
        return {
            "service": name,
            "backend": "journald",
            "exit_code": proc.returncode,
            "output": out,
            "truncated": truncated,
        }

    if _init_system() == "openrc" and name == "serverbridge":
        path = Path("/var/log/serverbridge.log")
        if not path.is_file():
            return {
                "service": name,
                "backend": "file",
                "output": "",
                "truncated": False,
                "message": "ServerBridge log file does not exist yet.",
            }

        with path.open("r", encoding="utf-8", errors="replace") as handle:
            recent = deque(handle, maxlen=lines)

        out, truncated = _truncate("".join(recent))
        return {
            "service": name,
            "backend": "file",
            "output": out,
            "truncated": truncated,
        }

    raise RuntimeError("No universal log backend is available for this service on the current init system")


def _read_process(pid: int) -> dict[str, Any] | None:
    status_path = Path("/proc") / str(pid) / "status"
    try:
        fields: dict[str, str] = {}
        for line in status_path.read_text(encoding="utf-8", errors="replace").splitlines():
            key, separator, value = line.partition(":")
            if separator and key in {"Name", "State", "PPid", "Uid", "VmRSS"}:
                fields[key] = value.strip()

        uid = int(fields.get("Uid", "-1").split()[0])
        try:
            user = pwd.getpwuid(uid).pw_name
        except (KeyError, ValueError):
            user = str(uid)

        rss_parts = fields.get("VmRSS", "0 kB").split()
        rss_kib = int(rss_parts[0]) if rss_parts and rss_parts[0].isdigit() else 0

        return {
            "pid": pid,
            "ppid": int(fields.get("PPid", "0")),
            "user": user,
            "state": fields.get("State", ""),
            "name": fields.get("Name", ""),
            "rss_kib": rss_kib,
        }
    except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
        return None


@mcp.tool()
def process_list(limit: int = 200) -> dict[str, Any]:
    """List processes from /proc without reading argv or environment variables."""
    limit = max(1, min(int(limit), 2000))

    processes: list[dict[str, Any]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        item = _read_process(int(entry.name))
        if item is not None:
            processes.append(item)

    processes.sort(key=lambda item: (-int(item["rss_kib"]), int(item["pid"])))
    truncated = len(processes) > limit

    return {
        "processes": processes[:limit],
        "count": len(processes),
        "truncated": truncated,
    }


if __name__ == "__main__":
    mcp.run()
