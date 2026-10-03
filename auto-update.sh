#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
LOG="/var/log/serverbridge-update.log"
PY="/opt/serverbridge/current/.venv/bin/python"
[[ -x "$PY" ]] || { printf '%s ERROR current runtime missing\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG"; exit 1; }
if "$PY" -m serverbridge.update_engine >>"$LOG" 2>&1; then
  printf '%s auto-update completed\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG"
else
  rc=$?
  printf '%s ERROR seamless updater failed rc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$rc" >>"$LOG"
  exit "$rc"
fi
