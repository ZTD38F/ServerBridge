#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

LOCK="/run/lock/serverbridge-auto-update.lock"
LOG="/var/log/serverbridge-update.log"
MAX_BYTES=$((5 * 1024 * 1024))

mkdir -p "$(dirname "$LOCK")"
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK"
  flock -n 9 || exit 0
else
  LOCKDIR="${LOCK}.d"
  mkdir "$LOCKDIR" 2>/dev/null || exit 0
  trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT INT TERM
fi

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

PYTHON="/opt/serverbridge/current/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  log "ERROR installed ServerBridge Python runtime not found"
  exit 1
fi

LOCAL_VERSION="$("$PYTHON" -c 'import serverbridge; print(serverbridge.__version__)')"
LATEST_TAG="$(curl -fsSL --retry 4 --retry-delay 2 --connect-timeout 15 --max-time 60 \
  https://api.github.com/repos/ZTD38F/ServerBridge/releases/latest |
  "$PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')"

if [[ "$LATEST_TAG" == "v$LOCAL_VERSION" ]]; then
  log "ok already current at $LOCAL_VERSION"
  exit 0
fi

[[ "$LATEST_TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
  log "ERROR invalid latest release tag: $LATEST_TAG"
  exit 1
}
log "update available: $LOCAL_VERSION -> $LATEST_TAG"

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
