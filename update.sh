#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

REPO="ZTD38F/ServerBridge"
TMP="$(mktemp -d /tmp/serverbridge-update.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT INT TERM

curl -fsSL --retry 4 --retry-delay 2 --connect-timeout 15 --max-time 60 \
  "https://github.com/$REPO/releases/latest/download/bootstrap.sh" \
  -o "$TMP/bootstrap.sh"

chmod 700 "$TMP/bootstrap.sh"
bash "$TMP/bootstrap.sh" "$@"
