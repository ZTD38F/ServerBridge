#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

REPO="ZTD38F/ServerBridge"
BRANCH="main"
TUNNEL_CLIENT_VERSION="${SERVERBRIDGE_TUNNEL_CLIENT_VERSION:-v0.0.15}"

INSTALL_ROOT="${SERVERBRIDGE_INSTALL_ROOT:-/opt/serverbridge}"
CONFIG_DIR="${SERVERBRIDGE_CONFIG_DIR:-/etc/serverbridge}"
STATE_DIR="${SERVERBRIDGE_STATE_DIR:-/var/lib/serverbridge}"
BIN_DIR="${SERVERBRIDGE_BIN_DIR:-/usr/local/lib/serverbridge}"
PROFILE_DIR="$CONFIG_DIR/tunnel-client"
PROFILE_NAME="serverbridge"
DRY_RUN=0
NO_START=0
AUTO_UPDATE="${SERVERBRIDGE_AUTO_UPDATE:-1}"
TUNNEL_ID="${SERVERBRIDGE_TUNNEL_ID:-${CONTROL_PLANE_TUNNEL_ID:-}}"
RUNTIME_KEY="${CONTROL_PLANE_API_KEY:-}"
SOURCE_SHA="${SERVERBRIDGE_SOURCE_SHA:-}"
SOURCE_DIR_OVERRIDE="${SERVERBRIDGE_SOURCE_DIR:-}"

TMP_DIR=""
NEW_RELEASE=""
PREVIOUS_CURRENT=""
BACKUP_DIR=""
TRANSACTION_STARTED=0
ROOT_EXISTED=0
CONFIG_EXISTED=0
STATE_EXISTED=0
BIN_EXISTED=0
PREVIOUS_SERVICE_ACTIVE=0
PREVIOUS_SERVICE_ENABLED=0
PREVIOUS_UPDATE_TIMER_ACTIVE=0
PREVIOUS_UPDATE_TIMER_ENABLED=0
CURRENT_STEP="startup"

if [[ -t 1 ]]; then
  RESET=$'\033[0m'; BOLD=$'\033[1m'; BLUE=$'\033[34m'
  GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; DIM=$'\033[2m'
else
  RESET=""; BOLD=""; BLUE=""; GREEN=""; YELLOW=""; RED=""; DIM=""
fi

say()  { printf '%b\n' "$*"; }
info() { say "${BLUE}●${RESET} $*"; }
ok()   { say "${GREEN}✓${RESET} $*"; }
warn() { say "${YELLOW}!${RESET} $*"; }
die()  { say "${RED}✗${RESET} $*" >&2; exit 1; }
step() {
  CURRENT_STEP="$2"
  say ""
  say "${BOLD}${BLUE}[$1/5]${RESET} ${BOLD}$2${RESET}"
}

usage() {
  cat <<'USAGE'
ServerBridge installer

Usage:
  sudo bash install.sh [options]

Options:
  --dry-run       Detect and validate only; do not modify the server.
  --no-start      Install and validate but do not start the service.
  --no-auto-update Do not install the daily stable auto-update job.
  --tunnel-id ID  Supply the tunnel ID non-interactively.
  --help          Show this help.

Secrets:
  CONTROL_PLANE_API_KEY may be supplied in the environment.
  There is intentionally no --api-key option, to reduce shell-history/process-list leakage.
USAGE
}

while (($#)); do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --no-start) NO_START=1 ;;
    --no-auto-update) AUTO_UPDATE=0 ;;
    --tunnel-id)
      shift
      (($#)) || die "--tunnel-id requires a value"
      TUNNEL_ID="$1"
      ;;
    --help|-h) usage; exit 0 ;;
    *) die "Unknown option: $1 (use --help)" ;;
  esac
  shift
done

have() { command -v "$1" >/dev/null 2>&1; }

backup_optional() {
  local path="$1" name="$2"
  if [[ -e "$path" || -L "$path" ]]; then
    touch "$BACKUP_DIR/$name.exists"
    cp -a "$path" "$BACKUP_DIR/$name"
  fi
}

restore_optional() {
  local path="$1" name="$2"
  rm -rf "$path" 2>/dev/null || true
  if [[ -e "$BACKUP_DIR/$name.exists" ]]; then
    mkdir -p "$(dirname "$path")"
    cp -a "$BACKUP_DIR/$name" "$path"
  fi
}

capture_previous_service_state() {
  PREVIOUS_SERVICE_ACTIVE=0
  PREVIOUS_SERVICE_ENABLED=0

  if [[ "$INIT" == "systemd" ]] && have systemctl &&
     [[ -f /etc/systemd/system/serverbridge.service ]]; then
    if systemctl is-active --quiet serverbridge.service; then
      PREVIOUS_SERVICE_ACTIVE=1
    fi
    if systemctl is-enabled --quiet serverbridge.service; then
      PREVIOUS_SERVICE_ENABLED=1
    fi
    if systemctl is-active --quiet serverbridge-update.timer; then
      PREVIOUS_UPDATE_TIMER_ACTIVE=1
    fi
    if systemctl is-enabled --quiet serverbridge-update.timer; then
      PREVIOUS_UPDATE_TIMER_ENABLED=1
    fi
  elif [[ "$INIT" == "openrc" ]] && have rc-service &&
       [[ -f /etc/init.d/serverbridge ]]; then
    if rc-service serverbridge status >/dev/null 2>&1; then
      PREVIOUS_SERVICE_ACTIVE=1
    fi
    if have rc-update && rc-update show 2>/dev/null | grep -Eq '(^|[[:space:]])serverbridge([[:space:]]|$)'; then
      PREVIOUS_SERVICE_ENABLED=1
    fi
  fi
}

restore_previous_service_state() {
  if [[ "$INIT" == "systemd" ]] && have systemctl; then
    systemctl daemon-reload >/dev/null 2>&1 || true

    if ((PREVIOUS_SERVICE_ENABLED)); then
      systemctl enable serverbridge.service >/dev/null 2>&1 || true
    else
      systemctl disable serverbridge.service >/dev/null 2>&1 || true
    fi

    if ((PREVIOUS_SERVICE_ACTIVE)); then
      systemctl restart serverbridge.service >/dev/null 2>&1 || true
    else
      systemctl stop serverbridge.service >/dev/null 2>&1 || true
    fi

    if ((PREVIOUS_UPDATE_TIMER_ENABLED)); then
      systemctl enable serverbridge-update.timer >/dev/null 2>&1 || true
    else
      systemctl disable serverbridge-update.timer >/dev/null 2>&1 || true
    fi
    if ((PREVIOUS_UPDATE_TIMER_ACTIVE)); then
      systemctl start serverbridge-update.timer >/dev/null 2>&1 || true
    else
      systemctl stop serverbridge-update.timer >/dev/null 2>&1 || true
    fi
  elif [[ "$INIT" == "openrc" ]] && have rc-service; then
    if have rc-update; then
      if ((PREVIOUS_SERVICE_ENABLED)); then
        rc-update add serverbridge default >/dev/null 2>&1 || true
      else
        rc-update del serverbridge default >/dev/null 2>&1 || true
      fi
    fi

    if ((PREVIOUS_SERVICE_ACTIVE)); then
      rc-service serverbridge restart >/dev/null 2>&1 || true
    else
      rc-service serverbridge stop >/dev/null 2>&1 || true
    fi
  fi
}

cleanup() {
  local rc=$?

  if ((rc != 0)); then
    warn "Failed during: $CURRENT_STEP."
  fi

  if ((rc != 0)) && ((TRANSACTION_STARTED == 1)); then
    warn "Installation failed; restoring the previous ServerBridge state."

    if [[ -n "$PREVIOUS_CURRENT" && -e "$PREVIOUS_CURRENT" ]]; then
      ln -sfn "$PREVIOUS_CURRENT" "$INSTALL_ROOT/current" || true
    else
      rm -f "$INSTALL_ROOT/current" || true
    fi

    restore_optional "$CONFIG_DIR/.serverbridge-managed" config.marker
    restore_optional "$CONFIG_DIR/runtime.env" runtime.env
    restore_optional "$CONFIG_DIR/serverbridge.env" serverbridge.env
    restore_optional "$CONFIG_DIR/control_plane_api_key" control_plane_api_key
    restore_optional "$CONFIG_DIR/router_token" router_token
    restore_optional "$CONFIG_DIR/backend_token" backend_token
    restore_optional "$CONFIG_DIR/network.env" network.env
    restore_optional "$CONFIG_DIR/network.sh" network.sh
    restore_optional "$PROFILE_DIR/$PROFILE_NAME.yaml" profile.yaml
    restore_optional "$BIN_DIR/tunnel-client" tunnel-client
    restore_optional "$BIN_DIR/launch-mcp" launch-mcp
    restore_optional "$BIN_DIR/auto-update" auto-update
    restore_optional /usr/local/sbin/serverbridgectl serverbridgectl
    restore_optional /etc/systemd/system/serverbridge-update.service update.service
    restore_optional /etc/systemd/system/serverbridge-update.timer update.timer
    restore_optional /etc/periodic/daily/serverbridge-update update.periodic
    restore_optional /etc/cron.daily/serverbridge-update update.cron

    if [[ ! -e "$BACKUP_DIR/systemd.service.exists" ]] && have systemctl; then
      systemctl disable serverbridge.service >/dev/null 2>&1 || true
    fi
    restore_optional /etc/systemd/system/serverbridge.service systemd.service
    if [[ ! -e "$BACKUP_DIR/supervisor.service.exists" ]] && have systemctl; then
      systemctl disable --now serverbridge-supervisor.service >/dev/null 2>&1 || true
      rm -f /etc/systemd/system/serverbridge-supervisor.service
    fi
    restore_optional /etc/systemd/system/serverbridge-supervisor.service supervisor.service
    if have systemctl; then systemctl daemon-reload >/dev/null 2>&1 || true; fi

    if [[ ! -e "$BACKUP_DIR/openrc.service.exists" ]] && have rc-update; then
      rc-update del serverbridge default >/dev/null 2>&1 || true
    fi
    restore_optional /etc/init.d/serverbridge openrc.service

    restore_previous_service_state

    if [[ -n "$NEW_RELEASE" && -d "$NEW_RELEASE" ]]; then
      rm -rf "$NEW_RELEASE" || true
    fi

    if ((ROOT_EXISTED == 0)); then rm -rf "$INSTALL_ROOT" || true; fi
    if ((CONFIG_EXISTED == 0)); then rm -rf "$CONFIG_DIR" || true; fi
    if ((STATE_EXISTED == 0)); then rm -rf "$STATE_DIR" || true; fi
    if ((BIN_EXISTED == 0)); then rm -rf "$BIN_DIR" || true; fi
  fi

  if [[ -n "$TMP_DIR" && -d "$TMP_DIR" ]]; then
    rm -rf "$TMP_DIR" || true
  fi
  trap - EXIT
  exit "$rc"
}
trap cleanup EXIT
trap 'die "Interrupted"' INT TERM

run() {
  if ((DRY_RUN)); then
    printf '%b\n' "${DIM}DRY-RUN:${RESET} $(printf '%q ' "$@")"
  else
    "$@"
  fi
}

run_checked() {
  local log
  log="$(mktemp /tmp/serverbridge-command.XXXXXX)"
  if "$@" >"$log" 2>&1; then
    rm -f "$log"
    return 0
  fi
  cat "$log" >&2
  rm -f "$log"
  return 1
}

require_root() {
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    die "Run as root/sudo. Recommended: curl -fsSL https://raw.githubusercontent.com/$REPO/$BRANCH/install.sh | sudo bash"
  fi
}

visible_input() {
  local prompt="$1" value
  [[ -r /dev/tty ]] || return 1
  printf '%b' "$prompt" >/dev/tty
  IFS= read -r value </dev/tty || return 1
  printf '%s' "$value"
}

secret_input() {
  local prompt="$1" value
  [[ -r /dev/tty ]] || return 1
  printf '%b' "$prompt" >/dev/tty
  IFS= read -r -s value </dev/tty || return 1
  printf '\n' >/dev/tty
  printf '%s' "$value"
}

load_existing_credentials() {
  if [[ -r "$CONFIG_DIR/runtime.env" ]]; then
    local old_id old_key
    old_id="$(grep -m1 '^CONTROL_PLANE_TUNNEL_ID=' "$CONFIG_DIR/runtime.env" 2>/dev/null | cut -d= -f2- || true)"
    old_key="$(grep -m1 '^CONTROL_PLANE_API_KEY=' "$CONFIG_DIR/runtime.env" 2>/dev/null | cut -d= -f2- || true)"
    [[ -n "$TUNNEL_ID" ]] || TUNNEL_ID="$old_id"
    [[ -n "$RUNTIME_KEY" ]] || RUNTIME_KEY="$old_key"
  fi
}

prompt_credentials() {
  say "${BOLD}ServerBridge${RESET}"
  say "${DIM}Private VPS → OpenAI Secure MCP Tunnel${RESET}"

  if [[ -z "$TUNNEL_ID" ]]; then
    say ""
    say "Tunnel: ${BLUE}https://platform.openai.com/settings/organization/tunnels${RESET}"
    TUNNEL_ID="$(visible_input "Tunnel ID: ")" ||
      die "No interactive terminal. Set SERVERBRIDGE_TUNNEL_ID."
  fi

  [[ "$TUNNEL_ID" =~ ^tunnel_[A-Za-z0-9_-]{8,}$ ]] ||
    die "Tunnel ID must look like tunnel_..."
  ok "Tunnel ID accepted."

  if ((DRY_RUN)) && [[ -z "$RUNTIME_KEY" ]]; then
    RUNTIME_KEY="dry-run-placeholder"
    info "Dry-run: runtime-key prompt skipped."
  elif [[ -z "$RUNTIME_KEY" ]]; then
    say "Runtime key: ${BLUE}https://platform.openai.com/settings/organization/api-keys${RESET}"
    RUNTIME_KEY="$(secret_input "Runtime API key: ")" ||
      die "No interactive terminal. Set CONTROL_PLANE_API_KEY."
  fi

  [[ "$RUNTIME_KEY" =~ ^[A-Za-z0-9._-]+$ ]] ||
    die "Runtime API key contains unsupported characters."

  ok "Runtime key received."
}

OS_ID="unknown"
OS_VERSION="unknown"
ARCH=""
PKG=""
INIT=""
PYTHON_BIN=""

detect_system() {
  [[ "$(uname -s)" == "Linux" ]] || die "ServerBridge currently supports Linux servers only."

  case "$(uname -m)" in
    x86_64|amd64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) die "Unsupported CPU architecture: $(uname -m). Supported: amd64, arm64." ;;
  esac

  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    OS_ID="${ID:-unknown}"
    OS_VERSION="${VERSION_ID:-unknown}"
  fi

  if have apt-get; then PKG="apt"
  elif have dnf; then PKG="dnf"
  elif have yum; then PKG="yum"
  elif have apk; then PKG="apk"
  elif have pacman; then PKG="pacman"
  elif have zypper; then PKG="zypper"
  else PKG="none"
  fi

  if have systemctl && [[ -d /run/systemd/system || "$(ps -p 1 -o comm= 2>/dev/null | tr -d ' ')" == "systemd" ]]; then
    INIT="systemd"
  elif have rc-service; then
    INIT="openrc"
  else
    INIT="manual"
  fi
}

python_ok() {
  local py="$1"
  "$py" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

select_python() {
  local py
  for py in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    if have "$py" && python_ok "$py"; then
      PYTHON_BIN="$(command -v "$py")"
      return 0
    fi
  done
  return 1
}

venv_ok() {
  local py="$1" d
  d="$(mktemp -d /tmp/serverbridge-venv.XXXXXX)"
  if "$py" -m venv "$d/venv" >/dev/null 2>&1; then
    rm -rf "$d"
    return 0
  fi
  rm -rf "$d"
  return 1
}

install_dependencies() {
  if ((DRY_RUN)); then
    info "Would install missing prerequisites with $PKG."
    return 0
  fi

  info "Installing missing prerequisites…"

  case "$PKG" in
    apt)
      run_checked env DEBIAN_FRONTEND=noninteractive apt-get \
        -o DPkg::Lock::Timeout=180 -o Acquire::Retries=4 update -qq
      run_checked env DEBIAN_FRONTEND=noninteractive apt-get \
        -o DPkg::Lock::Timeout=180 -o Acquire::Retries=4 \
        install -y --no-install-recommends \
        ca-certificates curl unzip tar gzip coreutils procps grep findutils python3 python3-venv python3-pip
      ;;
    dnf) run_checked dnf install -y ca-certificates curl unzip tar gzip coreutils procps-ng grep findutils python3 python3-pip ;;
    yum) run_checked yum install -y ca-certificates curl unzip tar gzip coreutils procps-ng grep findutils python3 python3-pip ;;
    apk) run_checked apk add --no-cache ca-certificates curl unzip tar gzip coreutils procps grep findutils python3 py3-pip py3-virtualenv ;;
    pacman) run_checked pacman -Sy --noconfirm --needed ca-certificates curl unzip tar gzip coreutils procps-ng grep findutils python python-pip ;;
    zypper) run_checked zypper --non-interactive install --no-recommends ca-certificates curl unzip tar gzip coreutils procps grep findutils python3 python3-pip python3-virtualenv ;;
    none) die "No supported package manager. Install curl, unzip, tar, sha256sum, grep, find, ps and Python >=3.10, then rerun." ;;
  esac

  ok "Prerequisites installed."
}

prereqs_ready() {
  select_python || return 1
  have curl && have unzip && have tar && have sha256sum &&
    have install && have grep && have find && have ps &&
    have df && have tail && venv_ok "$PYTHON_BIN"
}

check_resources() {
  local probe="$INSTALL_ROOT"
  local available

  while [[ ! -e "$probe" && "$probe" != "/" ]]; do
    probe="$(dirname "$probe")"
  done

  if have df && have tail; then
    available="$(df -Pk "$probe" | tail -n 1 | awk '{print $4}')"
    if [[ "$available" =~ ^[0-9]+$ ]] && ((available < 262144)); then
      die "Not enough free disk space near $INSTALL_ROOT. Need at least 256 MiB free."
    fi
  fi

  if [[ -r /proc/meminfo ]]; then
    local key value mem_available=""
    while read -r key value _; do
      if [[ "$key" == "MemAvailable:" ]]; then
        mem_available="$value"
        break
      fi
    done < /proc/meminfo

    if [[ "$mem_available" =~ ^[0-9]+$ ]] && ((mem_available < 131072)); then
      warn "Less than 128 MiB RAM is currently available; installation may need swap."
    fi
  fi
}

check_conflicts() {
  local managed=0
  [[ -e "$INSTALL_ROOT/.serverbridge-managed" ]] && managed=1

  if [[ -d "$INSTALL_ROOT" && $managed -eq 0 ]]; then
    die "$INSTALL_ROOT already exists but is not ServerBridge-managed."
  fi

  if ((managed == 0)); then
    if [[ -d "$CONFIG_DIR" && ! -e "$CONFIG_DIR/.serverbridge-managed" ]]; then
      die "$CONFIG_DIR already exists and is not marked as ServerBridge-managed."
    fi
    [[ ! -d "$STATE_DIR" ]] || die "$STATE_DIR already exists without a managed ServerBridge installation."
    [[ ! -d "$BIN_DIR" ]] || die "$BIN_DIR already exists without a managed ServerBridge installation."
    [[ ! -e /etc/systemd/system/serverbridge.service ]] ||
      die "A foreign /etc/systemd/system/serverbridge.service exists."
    [[ ! -e /etc/init.d/serverbridge ]] ||
      die "A foreign /etc/init.d/serverbridge exists."
    [[ ! -e /usr/local/sbin/serverbridgectl ]] ||
      die "A foreign /usr/local/sbin/serverbridgectl exists."
  fi
}

network_preflight() {
  curl -fsSIL --max-time 15 https://github.com/openai/tunnel-client/releases/latest >/dev/null ||
    die "Cannot reach GitHub releases over HTTPS."
  curl -fsSIL --max-time 15 https://pypi.org/simple/mcp/ >/dev/null ||
    die "Cannot reach PyPI over HTTPS."
  curl -sSIL --max-time 15 https://api.openai.com/ >/dev/null ||
    die "Cannot reach api.openai.com over HTTPS."
}

detect_local_source() {
  [[ -n "$SOURCE_DIR_OVERRIDE" ]] && return 0

  local script_path="${BASH_SOURCE[0]:-}" script_dir=""
  if [[ -n "$script_path" && -f "$script_path" ]]; then
    script_dir="$(cd "$(dirname "$script_path")" && pwd -P)"
    if [[ -f "$script_dir/pyproject.toml" && -d "$script_dir/serverbridge" ]]; then
      SOURCE_DIR_OVERRIDE="$script_dir"
    fi
  fi
}

resolve_source_sha() {
  local sha
  sha="$(curl -fsSL --retry 4 --retry-delay 2 --connect-timeout 15 --max-time 60     "https://api.github.com/repos/$REPO/commits/$BRANCH" |
    "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["sha"])')"

  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] ||
    die "Could not pin the ServerBridge source commit."

  printf '%s' "$sha"
}

fetch_source() {
  if [[ -n "$SOURCE_DIR_OVERRIDE" ]]; then
    local local_source
    local_source="$(cd "$SOURCE_DIR_OVERRIDE" && pwd -P)"
    [[ -f "$local_source/pyproject.toml" && -d "$local_source/serverbridge" ]] ||
      die "SERVERBRIDGE_SOURCE_DIR is not a valid ServerBridge source tree."
    printf '%s' "$local_source"
    return 0
  fi

  [[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] ||
    die "ServerBridge source commit is not pinned."

  local archive="$TMP_DIR/serverbridge.tar.gz"
  mkdir -p "$TMP_DIR/source"

  curl -fL --retry 4 --retry-delay 2 --connect-timeout 15 --max-time 180 \
    "https://github.com/$REPO/archive/$SOURCE_SHA.tar.gz" -o "$archive"

  tar -xzf "$archive" -C "$TMP_DIR/source" --strip-components=1

  [[ -f "$TMP_DIR/source/pyproject.toml" && -d "$TMP_DIR/source/serverbridge" ]] ||
    die "Downloaded ServerBridge repository archive is incomplete."

  printf '%s' "$TMP_DIR/source"
}

download_tunnel_client() {
  local tag="$1"
  local asset="tunnel-client-${tag}-linux-${ARCH}.zip"
  local base="https://github.com/openai/tunnel-client/releases/download/${tag}"
  local zip="$TMP_DIR/$asset"
  local sums="$TMP_DIR/SHA256SUMS.txt"
  local verify="$TMP_DIR/verify.sha256"
  local extract="$TMP_DIR/tunnel"

  curl -fL --retry 4 --retry-delay 2 --connect-timeout 15 --max-time 180 "$base/$asset" -o "$zip"
  curl -fL --retry 4 --retry-delay 2 --connect-timeout 15 --max-time 60 "$base/SHA256SUMS.txt" -o "$sums"

  grep -E "[[:space:]]${asset//./\\.}$" "$sums" > "$verify" ||
    die "Official checksum list does not contain $asset."

  (cd "$TMP_DIR" && sha256sum -c "$(basename "$verify")") >/dev/null ||
    die "tunnel-client SHA-256 verification failed."

  mkdir -p "$extract"
  unzip -q "$zip" -d "$extract"

  local binary
  binary="$(find "$extract" -type f -name tunnel-client -perm -u+x -print -quit)"
  [[ -n "$binary" ]] || binary="$(find "$extract" -type f -name tunnel-client -print -quit)"
  [[ -n "$binary" ]] || die "tunnel-client binary was not found in the archive."

  printf '%s' "$binary"
}

escape_systemd_env_value() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '%s' "$value"
}

write_network_env() {
  local name value shell_value
  : > "$CONFIG_DIR/network.env.new"
  : > "$CONFIG_DIR/network.sh.new"

  for name in \
    HTTP_PROXY HTTPS_PROXY NO_PROXY \
    http_proxy https_proxy no_proxy \
    CA_BUNDLE ENTERPRISE_CA_BUNDLE \
    TUNNEL_CLIENT_HTTP_PROXY CONTROL_PLANE_HTTP_PROXY
  do
    value="${!name:-}"
    [[ -n "$value" ]] || continue

    if [[ "$value" =~ [[:cntrl:]] ]]; then
      die "A preserved network environment value contains a control character."
    fi

    printf '%s="%s"\n' "$name" "$(escape_systemd_env_value "$value")" \
      >> "$CONFIG_DIR/network.env.new"

    shell_value="$("$PYTHON_BIN" -c 'import shlex,sys; print(shlex.quote(sys.argv[1]))' "$value")"
    printf 'export %s=%s\n' "$name" "$shell_value" >> "$CONFIG_DIR/network.sh.new"
  done

  chmod 600 "$CONFIG_DIR/network.env.new" "$CONFIG_DIR/network.sh.new"
  mv -f "$CONFIG_DIR/network.env.new" "$CONFIG_DIR/network.env"
  mv -f "$CONFIG_DIR/network.sh.new" "$CONFIG_DIR/network.sh"
}

validate_tunnel_client_binary() {
  local binary="$1" help flag

  "$binary" --version >/dev/null 2>&1 ||
    die "Downloaded tunnel-client cannot execute on this host."

  help="$("$binary" run --help 2>&1)" ||
    die "Downloaded tunnel-client does not provide a usable run command."
  for flag in --control-plane.api-key --control-plane.tunnel-id --mcp.server-url --mcp.extra-headers --health.listen-addr; do
    grep -Fq -- "$flag" <<<"$help" ||
      die "Latest tunnel-client is missing required HTTP transport flag: $flag"
  done
}

ensure_local_secret() {
  local path="$1"
  if [[ ! -s "$path" ]]; then
    "$PYTHON_BIN" - "$path" <<'PY'
from pathlib import Path
import secrets,sys
p=Path(sys.argv[1]);p.write_text(secrets.token_hex(32)+"\n");p.chmod(0o600)
PY
  fi
  chmod 600 "$path"
}

write_config() {
  install -d -m 700 "$CONFIG_DIR" "$PROFILE_DIR"
  touch "$CONFIG_DIR/.serverbridge-managed"
  chmod 600 "$CONFIG_DIR/.serverbridge-managed"

  local exec_enabled="${SERVERBRIDGE_ENABLE_EXEC:-}"
  local exec_timeout="${SERVERBRIDGE_EXEC_MAX_TIMEOUT:-}"
  if [[ -r "$CONFIG_DIR/serverbridge.env" ]]; then
    [[ -n "$exec_enabled" ]] || exec_enabled="$(grep -m1 '^SERVERBRIDGE_ENABLE_EXEC=' "$CONFIG_DIR/serverbridge.env" 2>/dev/null | cut -d= -f2- || true)"
    [[ -n "$exec_timeout" ]] || exec_timeout="$(grep -m1 '^SERVERBRIDGE_EXEC_MAX_TIMEOUT=' "$CONFIG_DIR/serverbridge.env" 2>/dev/null | cut -d= -f2- || true)"
  fi
  [[ -n "$exec_enabled" ]] || exec_enabled=0
  [[ "$exec_enabled" =~ ^(0|1|true|false|yes|no|on|off)$ ]] || die "SERVERBRIDGE_ENABLE_EXEC must be 0/1 or a boolean word."
  [[ -n "$exec_timeout" ]] || exec_timeout=900
  if [[ ! "$exec_timeout" =~ ^[0-9]+$ ]] || ((exec_timeout < 1 || exec_timeout > 3600)); then
    die "SERVERBRIDGE_EXEC_MAX_TIMEOUT must be 1-3600 seconds."
  fi

  printf '%s\n' "$RUNTIME_KEY" > "$CONFIG_DIR/control_plane_api_key.new"
  chmod 600 "$CONFIG_DIR/control_plane_api_key.new"
  mv -f "$CONFIG_DIR/control_plane_api_key.new" "$CONFIG_DIR/control_plane_api_key"
  ensure_local_secret "$CONFIG_DIR/router_token"
  ensure_local_secret "$CONFIG_DIR/backend_token"

  cat > "$CONFIG_DIR/runtime.env.new" <<EOF
CONTROL_PLANE_TUNNEL_ID=$TUNNEL_ID
CONTROL_PLANE_API_KEY_FILE=$CONFIG_DIR/control_plane_api_key
SERVERBRIDGE_ROUTER_TOKEN_FILE=$CONFIG_DIR/router_token
SERVERBRIDGE_BACKEND_TOKEN_FILE=$CONFIG_DIR/backend_token
EOF
  chmod 600 "$CONFIG_DIR/runtime.env.new"
  mv -f "$CONFIG_DIR/runtime.env.new" "$CONFIG_DIR/runtime.env"

  cat > "$CONFIG_DIR/serverbridge.env.new" <<EOF
SERVERBRIDGE_ALLOWED_ROOTS=/
SERVERBRIDGE_MAX_CAPTURE_BYTES=65536
SERVERBRIDGE_MAX_HASH_BYTES=67108864
SERVERBRIDGE_ENABLE_EXEC=$exec_enabled
SERVERBRIDGE_EXEC_MAX_TIMEOUT=$exec_timeout
SERVERBRIDGE_PROTECTED_PATHS=$CONFIG_DIR/runtime.env:$CONFIG_DIR/network.env:$CONFIG_DIR/network.sh:$CONFIG_DIR/control_plane_api_key:$CONFIG_DIR/router_token:$CONFIG_DIR/backend_token:$PROFILE_DIR
EOF
  chmod 600 "$CONFIG_DIR/serverbridge.env.new"
  mv -f "$CONFIG_DIR/serverbridge.env.new" "$CONFIG_DIR/serverbridge.env"

  write_network_env
}

install_launcher() {
  cat > "$BIN_DIR/launch-mcp" <<EOF
#!/usr/bin/env sh
set -eu
set -a
. "$CONFIG_DIR/serverbridge.env"
set +a
unset CONTROL_PLANE_API_KEY CONTROL_PLANE_TUNNEL_ID OPENAI_API_KEY OPENAI_ADMIN_KEY
exec "$INSTALL_ROOT/current/.venv/bin/python" -m serverbridge.server
EOF
  chmod 755 "$BIN_DIR/launch-mcp"
}

install_control_cli() {
  cat > /usr/local/sbin/serverbridgectl <<EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="$INSTALL_ROOT"
STATE="$STATE_DIR"
INIT="$INIT"

case "\${1:-check}" in
  check|doctor)
    ok=1
    if [[ "\$INIT" == systemd ]]; then
      systemctl is-active --quiet serverbridge-supervisor.service || { echo "FAIL supervisor"; ok=0; }
      systemctl is-active --quiet serverbridge.service || { echo "FAIL transport"; ok=0; }
    elif [[ "\$INIT" == openrc ]]; then
      rc-service serverbridge-supervisor status >/dev/null 2>&1 || { echo "FAIL supervisor"; ok=0; }
      rc-service serverbridge status >/dev/null 2>&1 || { echo "FAIL transport"; ok=0; }
    fi
    [[ -s "\$STATE/route.json" ]] || { echo "FAIL route state"; ok=0; }
    [[ -s "\$STATE/backend.pid" ]] || { echo "FAIL backend pid"; ok=0; }
    ((ok==1)) || exit 1
    echo "ServerBridge OK"
    ;;
  status|update-status)
    echo "ServerBridge"
    [[ ! -L "\$ROOT/current" ]] || echo "  current: \$(basename "\$(readlink -f "\$ROOT/current")")"
    [[ ! -s "\$STATE/route.json" ]] || { echo "  route:"; sed 's/^/    /' "\$STATE/route.json"; }
    [[ ! -s "\$STATE/update.json" ]] || { echo "  update:"; sed 's/^/    /' "\$STATE/update.json"; }
    if [[ "\$INIT" == systemd ]]; then
      systemctl --no-pager --full status serverbridge-supervisor.service serverbridge.service || true
    fi
    ;;
  logs)
    if [[ "\$INIT" == systemd ]]; then exec journalctl -u serverbridge-supervisor -u serverbridge -n "\${2:-100}" --no-pager
    else exec tail -n "\${2:-100}" /var/log/serverbridge*.log; fi
    ;;
  restart)
    if [[ "\$INIT" == systemd ]]; then systemctl restart serverbridge-supervisor.service; exec systemctl restart serverbridge.service
    elif [[ "\$INIT" == openrc ]]; then rc-service serverbridge-supervisor restart; exec rc-service serverbridge restart
    else exit 1; fi
    ;;
  update|update-now)
    exec "\$ROOT/current/.venv/bin/python" -m serverbridge.update_engine
    ;;
  stop)
    if [[ "\$INIT" == systemd ]]; then systemctl stop serverbridge.service; exec systemctl stop serverbridge-supervisor.service
    elif [[ "\$INIT" == openrc ]]; then rc-service serverbridge stop; exec rc-service serverbridge-supervisor stop
    else exit 0; fi
    ;;
  *) echo "Usage: serverbridgectl {check|doctor|status|update-status|logs [N]|restart|update|update-now|stop}" >&2; exit 2 ;;
esac
EOF
  chmod 755 /usr/local/sbin/serverbridgectl
}

install_auto_update() {
  [[ "$AUTO_UPDATE" =~ ^(0|1)$ ]] || die "SERVERBRIDGE_AUTO_UPDATE must be 0 or 1."

  if ((AUTO_UPDATE == 0)); then
    rm -f "$BIN_DIR/auto-update"
    case "$INIT" in
      systemd)
        systemctl disable --now serverbridge-update.timer >/dev/null 2>&1 || true
        systemctl stop serverbridge-update.service >/dev/null 2>&1 || true
        rm -f /etc/systemd/system/serverbridge-update.service /etc/systemd/system/serverbridge-update.timer
        systemctl daemon-reload
        ;;
      openrc)
        rm -f /etc/periodic/daily/serverbridge-update /etc/cron.daily/serverbridge-update
        ;;
    esac
    return 0
  fi

  chmod 755 "$NEW_RELEASE/auto-update.sh"
  install -m 755 "$NEW_RELEASE/auto-update.sh" "$BIN_DIR/auto-update"

  case "$INIT" in
    systemd)
      install -m 644 "$NEW_RELEASE/packaging/serverbridge-update.service" /etc/systemd/system/serverbridge-update.service
      install -m 644 "$NEW_RELEASE/packaging/serverbridge-update.timer" /etc/systemd/system/serverbridge-update.timer
      systemctl daemon-reload
      systemctl enable --now serverbridge-update.timer >/dev/null
      ;;
    openrc)
      if [[ -d /etc/periodic/daily ]]; then
        install -m 755 "$NEW_RELEASE/auto-update.sh" /etc/periodic/daily/serverbridge-update
      elif [[ -d /etc/cron.daily ]]; then
        install -m 755 "$NEW_RELEASE/auto-update.sh" /etc/cron.daily/serverbridge-update
      else
        warn "Auto-update requested, but no daily cron/periodic directory exists on this OpenRC host."
      fi
      ;;
    manual)
      warn "Auto-update requested, but no supported scheduler is available."
      ;;
  esac
}

create_systemd_service() {
  cat > /etc/systemd/system/serverbridge-supervisor.service <<EOF
[Unit]
Description=ServerBridge local MCP supervisor
Documentation=https://github.com/$REPO
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
EnvironmentFile=$CONFIG_DIR/serverbridge.env
EnvironmentFile=-$CONFIG_DIR/network.env
Environment=SERVERBRIDGE_BACKEND_TOKEN_FILE=$CONFIG_DIR/backend_token
ExecStart=$INSTALL_ROOT/current/.venv/bin/python -m serverbridge.supervisor
Restart=on-failure
RestartSec=2s
TimeoutStopSec=30s
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
ProtectClock=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictRealtime=true

[Install]
WantedBy=multi-user.target
EOF

  cat > /etc/systemd/system/serverbridge.service <<EOF
[Unit]
Description=ServerBridge OpenAI Secure MCP Tunnel
Documentation=https://github.com/$REPO
After=network-online.target serverbridge-supervisor.service
Wants=network-online.target
Requires=serverbridge-supervisor.service
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
EnvironmentFile=-$CONFIG_DIR/network.env
ExecStart=$BIN_DIR/tunnel-client run --control-plane.api-key file:$CONFIG_DIR/control_plane_api_key --control-plane.tunnel-id $TUNNEL_ID --mcp.server-url http://127.0.0.1:18766/mcp --mcp.extra-headers "X-Bridge-Token: file:$CONFIG_DIR/router_token" --health.listen-addr 127.0.0.1:18765
Restart=on-failure
RestartSec=5s
TimeoutStopSec=30s
KillMode=mixed
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
ProtectClock=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictRealtime=true

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable serverbridge-supervisor.service serverbridge.service >/dev/null
}

create_openrc_service() {
  cat > /etc/init.d/serverbridge-supervisor <<EOF
#!/sbin/openrc-run
name="ServerBridge supervisor"
description="ServerBridge local MCP supervisor"
command="$INSTALL_ROOT/current/.venv/bin/python"
command_args="-m serverbridge.supervisor"
command_background="yes"
pidfile="/run/serverbridge-supervisor.pid"
output_log="/var/log/serverbridge-supervisor.log"
error_log="/var/log/serverbridge-supervisor.log"
start_pre() {
  set -a
  . "$CONFIG_DIR/serverbridge.env"
  [ ! -r "$CONFIG_DIR/network.sh" ] || . "$CONFIG_DIR/network.sh"
  export SERVERBRIDGE_BACKEND_TOKEN_FILE="$CONFIG_DIR/backend_token"
  set +a
}
depend() { need net; after firewall; }
EOF
  chmod 755 /etc/init.d/serverbridge-supervisor

  cat > /etc/init.d/serverbridge <<EOF
#!/sbin/openrc-run
name="ServerBridge"
description="ServerBridge OpenAI Secure MCP Tunnel"
command="$BIN_DIR/tunnel-client"
command_args="run --control-plane.api-key file:$CONFIG_DIR/control_plane_api_key --control-plane.tunnel-id $TUNNEL_ID --mcp.server-url http://127.0.0.1:18766/mcp --mcp.extra-headers 'X-Bridge-Token: file:$CONFIG_DIR/router_token' --health.listen-addr 127.0.0.1:18765"
command_background="yes"
pidfile="/run/serverbridge.pid"
output_log="/var/log/serverbridge.log"
error_log="/var/log/serverbridge.log"
start_pre() { [ ! -r "$CONFIG_DIR/network.sh" ] || . "$CONFIG_DIR/network.sh"; }
depend() { need net serverbridge-supervisor; after firewall; }
EOF
  chmod 755 /etc/init.d/serverbridge
  rc-update add serverbridge-supervisor default >/dev/null
  rc-update add serverbridge default >/dev/null
}

start_and_verify() {
  case "$INIT" in
    systemd)
      systemctl restart serverbridge-supervisor.service
      systemctl restart serverbridge.service
      local stable=0
      for _ in {1..30}; do
        if systemctl is-active --quiet serverbridge-supervisor.service && systemctl is-active --quiet serverbridge.service; then
          stable=$((stable + 1))
          ((stable >= 5)) && return 0
        else
          stable=0
        fi
        sleep 1
      done
      journalctl -u serverbridge-supervisor.service -u serverbridge.service -n 100 --no-pager >&2 || true
      return 1
      ;;
    openrc)
      rc-service serverbridge-supervisor restart
      rc-service serverbridge restart
      sleep 3
      rc-service serverbridge-supervisor status && rc-service serverbridge status
      ;;
    manual)
      return 0
      ;;
  esac
}

require_root
load_existing_credentials

step 1 "Tunnel"
prompt_credentials

step 2 "Check server"
detect_system
check_conflicts
info "$OS_ID $OS_VERSION · $ARCH · $INIT"

if ! prereqs_ready; then
  install_dependencies
fi

if ((DRY_RUN)) && ! prereqs_ready; then
  warn "Some prerequisites are missing; a real run would install them."
else
  prereqs_ready || die "Prerequisites remain unavailable after package installation."
fi

check_resources
detect_local_source

if have curl; then
  network_preflight
  TUNNEL_TAG="$TUNNEL_CLIENT_VERSION"
  [[ "$TUNNEL_TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] ||
    die "SERVERBRIDGE_TUNNEL_CLIENT_VERSION must look like vX.Y.Z."

  if [[ -z "$SOURCE_DIR_OVERRIDE" ]]; then
    if [[ -z "$SOURCE_SHA" ]]; then
      SOURCE_SHA="$(resolve_source_sha)"
    elif [[ ! "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
      die "SERVERBRIDGE_SOURCE_SHA must be a 40-character Git commit SHA."
    fi
  fi
else
  ((DRY_RUN)) || die "curl is unavailable."
  TUNNEL_TAG="$TUNNEL_CLIENT_VERSION"
  [[ -n "$SOURCE_DIR_OVERRIDE" ]] || SOURCE_SHA="unresolved-in-dry-run"
  warn "curl is unavailable; live network checks were skipped in dry-run."
fi
ok "Server checks passed."

step 3 "Install"
if ((DRY_RUN)); then
  info "Would install ServerBridge and verified tunnel-client $TUNNEL_TAG."
else
  TMP_DIR="$(mktemp -d /tmp/serverbridge.XXXXXX)"
  SOURCE_DIR="$(fetch_source)"
  RELEASE_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
  NEW_RELEASE="$INSTALL_ROOT/releases/$RELEASE_ID"

  [[ -d "$INSTALL_ROOT" ]] && ROOT_EXISTED=1
  [[ -d "$CONFIG_DIR" ]] && CONFIG_EXISTED=1
  [[ -d "$STATE_DIR" ]] && STATE_EXISTED=1
  [[ -d "$BIN_DIR" ]] && BIN_EXISTED=1

  BACKUP_DIR="$TMP_DIR/rollback"
  mkdir -p "$BACKUP_DIR"

  capture_previous_service_state

  [[ -L "$INSTALL_ROOT/current" ]] &&
    PREVIOUS_CURRENT="$(readlink -f "$INSTALL_ROOT/current" || true)"

  backup_optional "$CONFIG_DIR/.serverbridge-managed" config.marker
  backup_optional "$CONFIG_DIR/runtime.env" runtime.env
  backup_optional "$CONFIG_DIR/serverbridge.env" serverbridge.env
  backup_optional "$CONFIG_DIR/control_plane_api_key" control_plane_api_key
  backup_optional "$CONFIG_DIR/router_token" router_token
  backup_optional "$CONFIG_DIR/backend_token" backend_token
  backup_optional "$CONFIG_DIR/network.env" network.env
  backup_optional "$CONFIG_DIR/network.sh" network.sh
  backup_optional "$PROFILE_DIR/$PROFILE_NAME.yaml" profile.yaml
  backup_optional "$BIN_DIR/tunnel-client" tunnel-client
  backup_optional "$BIN_DIR/launch-mcp" launch-mcp
  backup_optional "$BIN_DIR/auto-update" auto-update
  backup_optional /usr/local/sbin/serverbridgectl serverbridgectl
  backup_optional /etc/systemd/system/serverbridge.service systemd.service
  backup_optional /etc/systemd/system/serverbridge-supervisor.service supervisor.service
  backup_optional /etc/systemd/system/serverbridge-update.service update.service
  backup_optional /etc/systemd/system/serverbridge-update.timer update.timer
  backup_optional /etc/periodic/daily/serverbridge-update update.periodic
  backup_optional /etc/cron.daily/serverbridge-update update.cron
  backup_optional /etc/init.d/serverbridge openrc.service

  TRANSACTION_STARTED=1

  install -d -m 755 "$INSTALL_ROOT/releases" "$STATE_DIR" "$BIN_DIR"
  touch "$INSTALL_ROOT/.serverbridge-managed"
  install -d -m 755 "$NEW_RELEASE"

  cp -a "$SOURCE_DIR/." "$NEW_RELEASE/"
  rm -rf "$NEW_RELEASE/.git" || true

  "$PYTHON_BIN" -m venv "$NEW_RELEASE/.venv"
  [[ -s "$NEW_RELEASE/requirements.lock" ]] ||
    die "requirements.lock is missing from the release."

  "$NEW_RELEASE/.venv/bin/python" -m pip install \
    --disable-pip-version-check --no-input --retries 4 --timeout 30 \
    --require-hashes -r "$NEW_RELEASE/requirements.lock" >/dev/null

  "$NEW_RELEASE/.venv/bin/python" -m pip install \
    --disable-pip-version-check --no-input --no-deps \
    "$NEW_RELEASE" >/dev/null

  "$NEW_RELEASE/.venv/bin/python" -c 'import mcp, serverbridge; print(serverbridge.__version__)' >/dev/null

  TUNNEL_SOURCE="$(download_tunnel_client "$TUNNEL_TAG")"
  validate_tunnel_client_binary "$TUNNEL_SOURCE"
  install -m 755 "$TUNNEL_SOURCE" "$BIN_DIR/tunnel-client-$TUNNEL_TAG"
  ln -sfn "$BIN_DIR/tunnel-client-$TUNNEL_TAG" "$BIN_DIR/tunnel-client"
fi
ok "ServerBridge installed."

step 4 "Configure"
if ((DRY_RUN)); then
  info "Would create protected config, tunnel profile and $INIT autostart."
else
  write_config
  ln -sfn "$NEW_RELEASE" "$INSTALL_ROOT/current"
  install -d -m 700 "$STATE_DIR"
  "$PYTHON_BIN" - "$STATE_DIR/route.json" "$(basename "$NEW_RELEASE")" <<'PY'
import json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]);tmp=p.with_suffix(".tmp")
tmp.write_text(json.dumps({"generation":sys.argv[2],"port":18771},separators=(",",":"))+"\n")
os.replace(tmp,p);p.chmod(0o600)
PY

  install_control_cli
  install_auto_update

  case "$INIT" in
    systemd) create_systemd_service ;;
    openrc) create_openrc_service ;;
    manual) warn "No systemd/OpenRC: automatic 24/7 supervision was not configured." ;;
  esac
fi
ok "Tunnel configured."

step 5 "Verify"
if ((DRY_RUN)); then
  ok "Dry-run complete. No ServerBridge configuration or services were changed."
  TRANSACTION_STARTED=0
  exit 0
fi

if ((NO_START)); then
  ok "Installed and validated; start skipped by --no-start."
elif [[ "$INIT" == manual ]]; then
  ok "Installed and validated; automatic start is unavailable on this init system."
elif start_and_verify; then
  ok "Service is healthy."
else
  die "Service did not stay healthy; the previous installation will be restored."
fi

TRANSACTION_STARTED=0
NEW_RELEASE=""

say ""
say "${GREEN}${BOLD}✓ ServerBridge is ready${RESET}"
say ""
say "Next:"
say "  ${BLUE}https://chatgpt.com/#settings/Connectors${RESET}"
say "  Choose your tunnel → Scan tools"
say ""
say "Check anytime:"
say "  ${BOLD}sudo serverbridgectl check${RESET}"
