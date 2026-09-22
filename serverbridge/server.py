from __future__ import annotations

import hashlib
import itertools
import os
import platform
import pwd
import shutil
import socket
import subprocess
import signal
import tempfile
import time
from collections import deque
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from . import __version__

mcp = MCPServer("ServerBridge")

MAX_CAPTURE = int(os.getenv("SERVERBRIDGE_MAX_CAPTURE_BYTES", "65536"))
MAX_HASH_BYTES = int(os.getenv("SERVERBRIDGE_MAX_HASH_BYTES", str(64 * 1024 * 1024)))
EXEC_ENABLED = os.getenv("SERVERBRIDGE_ENABLE_EXEC", "0").strip().lower() in {"1", "true", "yes", "on"}
EXEC_MAX_TIMEOUT = max(1, min(int(os.getenv("SERVERBRIDGE_EXEC_MAX_TIMEOUT", "900")), 3600))



def _allowed_roots() -> list[Path]:
    raw = os.getenv("SERVERBRIDGE_ALLOWED_ROOTS", "/")
    roots = [Path(x.strip()).expanduser().resolve(strict=False) for x in raw.split(":") if x.strip()]
    return roots or [Path("/")]


def _protected_paths() -> list[Path]:
    raw = os.getenv(
        "SERVERBRIDGE_PROTECTED_PATHS",
        "/etc/serverbridge/runtime.env:/etc/serverbridge/network.env:/etc/serverbridge/network.sh:"
        "/etc/serverbridge/tunnel-client",
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


def _command_argv(argv: list[str]) -> list[str]:
    if not isinstance(argv, list) or not argv or len(argv) > 128:
        raise ValueError("argv must contain 1-128 arguments")
    normalized: list[str] = []
    total = 0
    for item in argv:
        if not isinstance(item, str) or not item or "\x00" in item:
            raise ValueError("argv contains an invalid argument")
        encoded = item.encode("utf-8", errors="strict")
        if len(encoded) > 8192:
            raise ValueError("one argv item is too large")
        total += len(encoded)
        normalized.append(item)
    if total > 65536:
        raise ValueError("argv is too large")
    return normalized


def _exec_environment() -> dict[str, str]:
    allowed = {
        "PATH", "HOME", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR",
        "USER", "LOGNAME", "SHELL", "TZ",
        "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    }
    return {key: value for key, value in os.environ.items() if key in allowed}


def _read_capture(handle: Any) -> tuple[str, bool]:
    handle.seek(0)
    data = handle.read(MAX_CAPTURE + 1)
    truncated = len(data) > MAX_CAPTURE
    visible = data[:MAX_CAPTURE]
    return visible.decode("utf-8", errors="replace") + ("\n…[truncated]" if truncated else ""), truncated


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


if EXEC_ENABLED:
    @mcp.tool()
    def run_command(argv: list[str], cwd: str = "/", timeout_seconds: int = 120) -> dict[str, Any]:
        """Run one argv-form command on the private server. Opt-in only; disabled unless SERVERBRIDGE_ENABLE_EXEC=1."""
        command = _command_argv(argv)
        target = _resolve_allowed(cwd)
        if not target.is_dir():
            raise NotADirectoryError(str(target))

        timeout = max(1, min(int(timeout_seconds), EXEC_MAX_TIMEOUT))
        started = time.monotonic()
        timed_out = False

        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            proc = subprocess.Popen(
                command,
                cwd=target,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                env=_exec_environment(),
                start_new_session=True,
                close_fds=True,
            )
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait(timeout=5)

            stdout, stdout_truncated = _read_capture(stdout_file)
            stderr, stderr_truncated = _read_capture(stderr_file)

        return {
            "executable": command[0],
            "argument_count": len(command),
            "cwd": str(target),
            "exit_code": None if timed_out else proc.returncode,
            "timed_out": timed_out,
            "timeout_seconds": timeout,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }


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
