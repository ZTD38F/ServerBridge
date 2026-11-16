"""Offline regression: cached release sources must match the verified artifact."""
from __future__ import annotations

import hashlib
import io
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import patch

from serverbridge import update_engine as updater


COMMIT = "a" * 40
TAG = "v0.5.9"
ARCHIVE = f"ServerBridge-{TAG}.tar.gz"
FILES = {
    "serverbridge/http_runtime.py": b"safe runtime\n",
    "README.md": b"release documentation\n",
}


def archive() -> bytes:
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as tar:
        for name, payload in FILES.items():
            info = tarfile.TarInfo(f"ServerBridge-{TAG}/{name}")
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return data.getvalue()


def test_cached_release_integrity() -> None:
    content = archive()
    manifest = f"{hashlib.sha256(content).hexdigest()}  {ARCHIVE}\n".encode()
    release = {
        "tag_name": TAG,
        "draft": False,
        "prerelease": False,
        "assets": [
            {"name": ARCHIVE, "browser_download_url": "https://example.invalid/archive"},
            {"name": "SHA256SUMS.txt", "browser_download_url": "https://example.invalid/sums"},
        ],
    }

    def fake_api(url: str):
        return release if url.endswith("/releases/latest") else {"sha": COMMIT}

    def fake_download(url: str, path: Path) -> None:
        Path(path).write_bytes(content if url.endswith("archive") else manifest)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        dest = root / "releases" / COMMIT
        for name, body in FILES.items():
            path = dest / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        (dest / ".venv" / "bin").mkdir(parents=True)
        (dest / ".venv" / "bin" / "python").write_bytes(b"local python fixture")
        with (
            patch.object(updater, "ROOT", root),
            patch.object(updater, "api", side_effect=fake_api),
            patch.object(updater, "download", side_effect=fake_download),
        ):
            result = updater.stage_latest()
            assert result == (COMMIT, dest, TAG), result
            (dest / "README.md").write_bytes(b"TAMPERED\n")
            try:
                updater.stage_latest()
            except RuntimeError as exc:
                assert "integrity" in str(exc).lower(), str(exc)
            else:
                raise AssertionError("A tampered cached release was silently trusted")
            (dest / "README.md").unlink()
            try:
                updater.stage_latest()
            except RuntimeError:
                pass
            else:
                raise AssertionError("A partially missing cached release was trusted")


if __name__ == "__main__":
    test_cached_release_integrity()
    print("Cached-release integrity tests passed")
