#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="${SERVERBRIDGE_INSTALL_ROOT:-/opt/serverbridge}"
STATE="${SERVERBRIDGE_STATE_DIR:-/var/lib/serverbridge}"
BIN="${SERVERBRIDGE_BIN_DIR:-/usr/local/lib/serverbridge}"
LOG="${SERVERBRIDGE_UPDATE_LOG:-/var/log/serverbridge-update.log}"
PY="${SERVERBRIDGE_CURRENT_PY:-$ROOT/current/.venv/bin/python}"
[[ -x "$PY" ]] || { printf '%s ERROR current runtime missing\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG"; exit 1; }

# Steady-state HEAD redirect check avoids unauthenticated REST API quota costs.
# Any uncertain state falls back to the existing transactional updater.
already_current() {
  local final_url tag version generation wanted pinned installed state
  final_url="$(curl -fsSLI -o /dev/null -w '%{url_effective}' --connect-timeout 5 --max-time 15 \
    https://github.com/ZTD38F/ServerBridge/releases/latest)" || return 1
  [[ "$final_url" =~ ^https://github[.]com/ZTD38F/ServerBridge/releases/tag/(v[0-9]+[.][0-9]+[.][0-9]+)$ ]] || return 1
  tag="${BASH_REMATCH[1]}"
  version="$("$PY" -c 'import serverbridge; print("v"+serverbridge.__version__)' 2>/dev/null)" || return 1
  [[ "$tag" == "$version" ]] || return 1
  generation="$(basename "$(readlink -f "$ROOT/current")")" || return 1
  [[ -r "$STATE/supervisor-generation" ]] || return 1
  IFS= read -r wanted < "$STATE/supervisor-generation" || [[ -n "$wanted" ]]
  [[ "$generation" == "$wanted" ]] || return 1
  [[ -r "$ROOT/current/TUNNEL_CLIENT_VERSION" ]] || return 1
  IFS= read -r pinned < "$ROOT/current/TUNNEL_CLIENT_VERSION" || [[ -n "$pinned" ]]
  [[ -x "$BIN/tunnel-client" ]] || return 1
  installed="$("$BIN/tunnel-client" --version 2>/dev/null)" || return 1
  installed="${installed%% *}"
  installed="${installed%%+*}"
  installed="${installed#v}"
  [[ "${pinned#v}" == "$installed" ]] || return 1
  if [[ -r "$STATE/update.json" ]]; then
    state="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("phase",""))' "$STATE/update.json" 2>/dev/null)" || return 1
    [[ "$state" == "COMMITTED" ]] || return 1
  fi
  return 0
}

if already_current; then
  exit 0
fi

if "$PY" -m serverbridge.update_engine >>"$LOG" 2>&1; then
  printf '%s auto-update completed\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG"
else
  rc=$?
  printf '%s ERROR transactional updater failed rc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$rc" >>"$LOG"
  exit "$rc"
fi
