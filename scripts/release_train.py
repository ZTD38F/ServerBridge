#!/usr/bin/env python3
"""Plan immutable release-candidate metadata from a successful main CI.

This command never publishes, merges, deploys, or talks to GitHub.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
PATTERNS = {
    "pyproject.toml": re.compile(r'^version = "([^"]+)"$', re.M),
    "plugin.json": re.compile(r'^  "version": "([^"]+)",$', re.M),
    "serverbridge/__init__.py": re.compile(r'^__version__ = "([^"]+)"$', re.M),
}


def semver(v: str) -> tuple[int, int, int]:
    if not isinstance(v, str) or not SEMVER.fullmatch(v):
        raise ValueError("version must be strict major.minor.patch")
    return tuple(map(int, v.split(".")))


def sources(root: Path) -> tuple[str, dict[str, str]]:
    data = {}
    values = set()
    for name, pattern in PATTERNS.items():
        raw = (root / name).read_text(encoding="utf-8")
        found = pattern.findall(raw)
        if len(found) != 1:
            raise ValueError(f"{name}: expected one version assignment")
        data[name] = raw
        values.add(found[0])
    if len(values) != 1:
        raise ValueError("version mismatch across package, plugin and runtime")
    current = values.pop()
    semver(current)
    return current, data


def plan(root: Path, tag: str, source_sha: str) -> dict[str, str]:
    if not SHA.fullmatch(source_sha):
        raise ValueError("invalid full lowercase source SHA")
    if not tag.startswith("v"):
        raise ValueError("published version must start with v")
    published = semver(tag[1:])
    current, _ = sources(root)
    if semver(current) < published:
        raise ValueError("repository version older than latest published release")
    if semver(current) > published:
        return {"action": "await_release", "current": current,
                "published": tag, "source_sha": source_sha}
    next_version = f"{published[0]}.{published[1]}.{published[2]+1}"
    return {"action": "propose", "current": current, "published": tag,
            "version": next_version, "branch": f"automated-release/v{next_version}",
            "source_sha": source_sha}


def apply(root: Path, decision: dict[str, str], date: str) -> list[str]:
    if decision["action"] != "propose":
        raise ValueError("not a proposed release")
    dt.date.fromisoformat(date)
    current, existing = sources(root)
    if current != decision["current"]:
        raise ValueError("version changed since planning")
    new = decision["version"]
    edited = {}
    for name, content in existing.items():
        before = PATTERNS[name]
        edited[name], count = before.subn(
            lambda m: m.group(0).replace(f'"{current}"', f'"{new}"'), content, count=1
        )
        if count != 1:
            raise ValueError(f"{name}: cannot update version")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    header = f"## {new} — {date}"
    if re.search(r"^## Unreleased\s*$", changelog, re.M):
        edited["CHANGELOG.md"] = re.sub(r"^## Unreleased\s*$",
                                        header, changelog, count=1, flags=re.M)
    elif changelog.startswith("# Changelog\n"):
        # Use SHA instead of injecting untrusted commit messages into release notes.
        note = f"- Automated candidate from verified main commit {decision['source_sha'][:12]}."
        edited["CHANGELOG.md"] = "# Changelog\n\n" + header + "\n\n" + note + "\n" + changelog[len("# Changelog\n"):]
    else:
        raise ValueError("unrecognized changelog header")
    # Mutate only four files in the ephemeral GitHub workflow checkout.
    for name, content in edited.items():
        p = root / name
        tmp = p.with_name("." + p.name + ".release-train-tmp")
        if tmp.exists():
            raise ValueError(f"{name}: leftover temporary file")
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.chmod(p.stat().st_mode & 0o777)
            tmp.replace(p)
        finally:
            tmp.unlink(missing_ok=True)
    if sources(root)[0] != new:
        raise ValueError("independent version readback failed")
    return sorted(edited)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["plan", "apply"])
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--published", required=True)
    ap.add_argument("--source-sha", required=True)
    ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    ns = ap.parse_args()
    try:
        p = plan(ns.root, ns.published, ns.source_sha)
        if ns.mode == "apply" and p["action"] == "propose":
            p["files"] = apply(ns.root, p, ns.date)
        print(json.dumps(p, sort_keys=True))
        return 0
    except (ValueError, OSError) as e:
        print(f"release-train: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
