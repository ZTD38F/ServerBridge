#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

REPO="ZTD38F/ServerBridge"
BRANCH="main"

command -v curl >/dev/null 2>&1 || {
  printf 'ServerBridge needs curl for the one-line bootstrap.\n' >&2
  exit 1
}

json="$(curl -fsSL --retry 4 --retry-delay 2 --connect-timeout 15 --max-time 60 \
  "https://api.github.com/repos/$REPO/commits/$BRANCH")"

if [[ "$json" =~ \"sha\"[[:space:]]*:[[:space:]]*\"([0-9a-f]{40})\" ]]; then
  source_sha="${BASH_REMATCH[1]}"
else
  printf 'Could not resolve the current ServerBridge commit.\n' >&2
  exit 1
fi

tmp="${TMPDIR:-/tmp}/serverbridge-bootstrap.$$.$RANDOM.sh"
trap 'rm -f "$tmp"' EXIT INT TERM

curl -fsSL --retry 4 --retry-delay 2 --connect-timeout 15 --max-time 60 \
  "https://raw.githubusercontent.com/$REPO/$source_sha/install.sh" \
  -o "$tmp"

chmod 700 "$tmp"
SERVERBRIDGE_SOURCE_SHA="$source_sha" bash "$tmp" "$@"
