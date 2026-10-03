#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

LOCK="/run/lock/serverbridge-auto-update.lock"
LOG="/var/log/serverbridge-update.log"
MAX_BYTES=$((5 * 1024 * 1024))

mkdir -p "$(dirname "$LOCK")"
exec 9>"$LOCK"
flock -n 9 || exit 0

rotate_log() {
  [[ -f "$LOG" ]] || return 0
  local size
  size="$(stat -c %s "$LOG" 2>/dev/null || echo 0)"
  ((size <= MAX_BYTES)) && return 0
  for i in 3 2 1; do
    if ((i == 1)); then
      [[ ! -f "$LOG" ]] || mv -f "$LOG" "$LOG.1"
    else
      [[ ! -f "$LOG.$((i-1))" ]] || mv -f "$LOG.$((i-1))" "$LOG.$i"
    fi
  done
}

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG"
}

rotate_log
log "auto-update check started"

if /usr/local/sbin/serverbridgectl update >>"$LOG" 2>&1; then
  if /usr/local/sbin/serverbridgectl check >>"$LOG" 2>&1; then
    log "auto-update check completed successfully"
  else
    log "ERROR: post-update health check failed"
    exit 1
  fi
else
  log "ERROR: updater failed; installer rollback should have preserved the previous working release"
  exit 1
fi
