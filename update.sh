#!/usr/bin/env bash
set -Eeuo pipefail

REPO="ZTD38F/ServerBridge"
BRANCH="main"
TMP="$(mktemp -d /tmp/serverbridge-update.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

curl -fL --retry 4 --retry-delay 2 --connect-timeout 15   "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz"   -o "$TMP/source.tar.gz"

mkdir -p "$TMP/source"
tar -xzf "$TMP/source.tar.gz" -C "$TMP/source" --strip-components=1

SERVERBRIDGE_SOURCE_DIR="$TMP/source" bash "$TMP/source/install.sh" "$@"
