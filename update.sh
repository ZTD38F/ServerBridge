#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ -x /opt/serverbridge/current/.venv/bin/python ]] &&
   /opt/serverbridge/current/.venv/bin/python -c 'import serverbridge.update_engine' >/dev/null 2>&1; then
  exec /opt/serverbridge/current/.venv/bin/python -m serverbridge.update_engine "$@"
fi

REPO="ZTD38F/ServerBridge"
TMP="$(mktemp -d /tmp/serverbridge-update.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT INT TERM
BASE="https://github.com/$REPO/releases/latest/download"
curl -fsSL --retry 4 --retry-delay 2 --connect-timeout 15 --max-time 60 "$BASE/bootstrap.sh" -o "$TMP/bootstrap.sh"
curl -fsSL --retry 4 --retry-delay 2 --connect-timeout 15 --max-time 60 "$BASE/SHA256SUMS.txt" -o "$TMP/SHA256SUMS.txt"
grep -E '[[:space:]]bootstrap\.sh$' "$TMP/SHA256SUMS.txt" >"$TMP/bootstrap.sha256" ||
  { echo "Release checksum does not cover bootstrap.sh" >&2; exit 1; }
(cd "$TMP" && sha256sum -c bootstrap.sha256)
chmod 700 "$TMP/bootstrap.sh"
exec bash "$TMP/bootstrap.sh" "$@"
