#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

REPO="ZTD38F/ServerBridge"
BRANCH="main"
CHANNEL="${SERVERBRIDGE_CHANNEL:-stable}"

command -v curl >/dev/null 2>&1 || {
  printf 'ServerBridge needs curl for the bootstrap.\n' >&2
  exit 1
}

api_get() {
  curl -fsSL --retry 4 --retry-delay 2 --connect-timeout 15 --max-time 60 "$1"
}

case "$CHANNEL" in
  stable)
    release_json="$(api_get "https://api.github.com/repos/$REPO/releases/latest")"
    if [[ "$release_json" =~ \"tag_name\"[[:space:]]*:[[:space:]]*\"(v[0-9]+\.[0-9]+\.[0-9]+)\" ]]; then
      source_ref="${BASH_REMATCH[1]}"
    else
      printf 'Could not resolve the latest stable ServerBridge release.\n' >&2
      exit 1
    fi
    ;;
  edge)
    source_ref="$BRANCH"
    ;;
  *)
    printf 'SERVERBRIDGE_CHANNEL must be stable or edge.\n' >&2
    exit 1
    ;;
esac

commit_json="$(api_get "https://api.github.com/repos/$REPO/commits/$source_ref")"
if [[ "$commit_json" =~ \"sha\"[[:space:]]*:[[:space:]]*\"([0-9a-f]{40})\" ]]; then
  source_sha="${BASH_REMATCH[1]}"
else
  printf 'Could not resolve the ServerBridge source commit.\n' >&2
  exit 1
fi

tmp="${TMPDIR:-/tmp}/serverbridge-bootstrap.$$.$RANDOM.sh"
trap 'rm -f "$tmp"' EXIT INT TERM

curl -fsSL --retry 4 --retry-delay 2 --connect-timeout 15 --max-time 60 \
  "https://raw.githubusercontent.com/$REPO/$source_sha/install.sh" \
  -o "$tmp"

chmod 700 "$tmp"

if [[ "$CHANNEL" == stable ]]; then
  printf 'ServerBridge %s\n' "$source_ref"
else
  printf 'ServerBridge edge (%s)\n' "${source_sha:0:12}"
fi

SERVERBRIDGE_SOURCE_SHA="$source_sha" bash "$tmp" "$@"
