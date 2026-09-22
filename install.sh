#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

REPO="ZTD38F/ServerBridge"
BRANCH="main"
TUNNEL_CLIENT_VERSION="${SERVERBRIDGE_TUNNEL_CLIENT_VERSION:-v0.0.14}"

INSTALL_ROOT="${SERVERBRIDGE_INSTALL_ROOT:-/opt/serverbridge}"
CONFIG_DIR="${SERVERBRIDGE_CONFIG_DIR:-/etc/serverbridge}"
STATE_DIR="${SERVERBRIDGE_STATE_DIR:-/var/lib/serverbridge}"
BIN_DIR="${SERVERBRIDGE_BIN_DIR:-/usr/local/lib/serverbridge}"
PROFILE_DIR="$CONFIG_DIR/tunnel-client"
PROFILE_NAME="serverbridge"
DRY_RUN=0
NO_START=0
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
    restore_optional "$CONFIG_DIR/network.env" network.env
    restore_optional "$CONFIG_DIR/network.sh" network.sh
    restore_optional "$PROFILE_DIR/$PROFILE_NAME.yaml" profile.yaml
    restore_optional "$BIN_DIR/tunnel-client" tunnel-client
    restore_optional "$BIN_DIR/launch-mcp" launch-mcp
    restore_optional /usr/local/sbin/serverbridgectl serverbridgectl

    if [[ ! -e "$BACKUP_DIR/systemd.service.exists" ]] && have systemctl; then
      systemctl disable serverbridge.service >/dev/null 2>&1 || true
    fi
    restore_optional /etc/systemd/system/serverbridge.service systemd.service

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

  help="$("$binary" init --help 2>&1)" ||
    die "Downloaded tunnel-client does not provide a usable init command."
  for flag in --profile-dir --tunnel-id --mcp-command --health-listen-addr; do
    grep -Fq -- "$flag" <<<"$help" ||
      die "Latest tunnel-client is missing required init flag: $flag"
  done

  help="$("$binary" doctor --help 2>&1)" ||
    die "Downloaded tunnel-client does not provide a usable doctor command."
  grep -Fq -- "--profile-dir" <<<"$help" ||
    die "Latest tunnel-client is missing doctor --profile-dir."

  help="$("$binary" run --help 2>&1)" ||
    die "Downloaded tunnel-client does not provide a usable run command."
  grep -Fq -- "--profile-dir" <<<"$help" ||
    die "Latest tunnel-client is missing run --profile-dir."
}

write_config() {
  install -d -m 700 "$CONFIG_DIR" "$PROFILE_DIR"
  touch "$CONFIG_DIR/.serverbridge-managed"
  chmod 600 "$CONFIG_DIR/.serverbridge-managed"

  cat > "$CONFIG_DIR/runtime.env.new" <<EOF
CONTROL_PLANE_API_KEY=$RUNTIME_KEY
CONTROL_PLANE_TUNNEL_ID=$TUNNEL_ID
EOF
  chmod 600 "$CONFIG_DIR/runtime.env.new"
  mv -f "$CONFIG_DIR/runtime.env.new" "$CONFIG_DIR/runtime.env"

  cat > "$CONFIG_DIR/serverbridge.env.new" <<EOF
SERVERBRIDGE_ALLOWED_ROOTS=/
SERVERBRIDGE_MAX_CAPTURE_BYTES=65536
SERVERBRIDGE_MAX_HASH_BYTES=67108864
SERVERBRIDGE_PROTECTED_PATHS=$CONFIG_DIR/runtime.env:$CONFIG_DIR/network.env:$CONFIG_DIR/network.sh:$PROFILE_DIR
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
CONFIG_DIR="$CONFIG_DIR"
PROFILE_DIR="$PROFILE_DIR"
PROFILE_NAME="$PROFILE_NAME"
TUNNEL="$BIN_DIR/tunnel-client"
INIT="$INIT"

load_env() {
  set -a
  . "\$CONFIG_DIR/runtime.env"
  . "\$CONFIG_DIR/serverbridge.env"
  [[ ! -r "\$CONFIG_DIR/network.sh" ]] || . "\$CONFIG_DIR/network.sh"
  set +a
}

doctor() {
  load_env
  "\$TUNNEL" doctor --profile-dir "\$PROFILE_DIR" --profile "\$PROFILE_NAME" --explain
}

case "\${1:-check}" in
  check)
    load_env
    printf 'ServerBridge\n'

    service_ok=1
    if [[ "\$INIT" == systemd ]]; then
      if systemctl is-active --quiet serverbridge; then
        printf '  ✓ service running\n'
      else
        printf '  ✗ service not running\n'
        service_ok=0
      fi
    elif [[ "\$INIT" == openrc ]]; then
      if rc-service serverbridge status >/dev/null 2>&1; then
        printf '  ✓ service running\n'
      else
        printf '  ✗ service not running\n'
        service_ok=0
      fi
    else
      printf '  ! no supported service manager\n'
    fi

    log="\$(mktemp /tmp/serverbridge-doctor.XXXXXX)"
    if "\$TUNNEL" doctor --profile-dir "\$PROFILE_DIR" --profile "\$PROFILE_NAME" --explain >"\$log" 2>&1; then
      printf '  ✓ tunnel profile valid\n'
    else
      printf '  ✗ tunnel validation failed\n'
      cat "\$log"
      rm -f "\$log"
      exit 1
    fi
    rm -f "\$log"
    ((service_ok == 1)) || exit 1
    ;;
  doctor)
    doctor
    ;;
  status)
    if [[ "\$INIT" == systemd ]]; then systemctl status serverbridge --no-pager || true
    elif [[ "\$INIT" == openrc ]]; then rc-service serverbridge status || true
    else echo "No supported service manager configured."; fi
    ;;
  logs)
    if [[ "\$INIT" == systemd ]]; then exec journalctl -u serverbridge -n "\${2:-100}" --no-pager
    else exec tail -n "\${2:-100}" /var/log/serverbridge.log; fi
    ;;
  restart)
    if [[ "\$INIT" == systemd ]]; then exec systemctl restart serverbridge
    elif [[ "\$INIT" == openrc ]]; then exec rc-service serverbridge restart
    else echo "No supported service manager." >&2; exit 1; fi
    ;;
  stop)
    if [[ "\$INIT" == systemd ]]; then exec systemctl stop serverbridge
    elif [[ "\$INIT" == openrc ]]; then exec rc-service serverbridge stop
    else exit 0; fi
    ;;
  *) echo "Usage: serverbridgectl {check|status|doctor|logs [N]|restart|stop}" >&2; exit 2 ;;
esac
EOF
  chmod 755 /usr/local/sbin/serverbridgectl
}

create_systemd_service() {
  cat > /etc/systemd/system/serverbridge.service <<EOF
[Unit]
Description=ServerBridge OpenAI Secure MCP Tunnel
Documentation=https://github.com/$REPO
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
EnvironmentFile=$CONFIG_DIR/runtime.env
EnvironmentFile=$CONFIG_DIR/serverbridge.env
EnvironmentFile=-$CONFIG_DIR/network.env
ExecStart=$BIN_DIR/tunnel-client run --profile-dir $PROFILE_DIR --profile $PROFILE_NAME
Restart=on-failure
RestartSec=5s
TimeoutStopSec=30s
KillMode=mixed

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable serverbridge.service >/dev/null
}

create_openrc_service() {
  cat > /etc/init.d/serverbridge <<EOF
#!/sbin/openrc-run
name="ServerBridge"
description="ServerBridge OpenAI Secure MCP Tunnel"
command="$BIN_DIR/tunnel-client"
command_args="run --profile-dir $PROFILE_DIR --profile $PROFILE_NAME"
command_background="yes"
pidfile="/run/serverbridge.pid"
output_log="/var/log/serverbridge.log"
error_log="/var/log/serverbridge.log"

start_pre() {
  set -a
  . "$CONFIG_DIR/runtime.env"
  . "$CONFIG_DIR/serverbridge.env"
  [ ! -r "$CONFIG_DIR/network.sh" ] || . "$CONFIG_DIR/network.sh"
  set +a
}

depend() {
  need net
  after firewall
}
EOF

  chmod 755 /etc/init.d/serverbridge
  rc-update add serverbridge default >/dev/null
}

start_and_verify() {
  case "$INIT" in
    systemd)
      systemctl restart serverbridge.service
      local stable=0
      for _ in {1..25}; do
        if systemctl is-active --quiet serverbridge.service; then
          stable=$((stable + 1))
          ((stable >= 5)) && return 0
        else
          stable=0
        fi
        sleep 1
      done
      journalctl -u serverbridge.service -n 80 --no-pager >&2 || true
      return 1
      ;;
    openrc)
      rc-service serverbridge restart
      sleep 3
      rc-service serverbridge status
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
  TUNNEL_TAG="$(latest_tunnel_tag)"

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
  backup_optional "$CONFIG_DIR/network.env" network.env
  backup_optional "$CONFIG_DIR/network.sh" network.sh
  backup_optional "$PROFILE_DIR/$PROFILE_NAME.yaml" profile.yaml
  backup_optional "$BIN_DIR/tunnel-client" tunnel-client
  backup_optional "$BIN_DIR/launch-mcp" launch-mcp
  backup_optional /usr/local/sbin/serverbridgectl serverbridgectl
  backup_optional /etc/systemd/system/serverbridge.service systemd.service
  backup_optional /etc/init.d/serverbridge openrc.service

  TRANSACTION_STARTED=1

  install -d -m 755 "$INSTALL_ROOT/releases" "$STATE_DIR" "$BIN_DIR"
  touch "$INSTALL_ROOT/.serverbridge-managed"
  install -d -m 755 "$NEW_RELEASE"

  cp -a "$SOURCE_DIR/." "$NEW_RELEASE/"
  rm -rf "$NEW_RELEASE/.git" || true

  "$PYTHON_BIN" -m venv "$NEW_RELEASE/.venv"
  "$NEW_RELEASE/.venv/bin/python" -m pip install     --disable-pip-version-check --no-input --retries 4 --timeout 30     --upgrade "pip<26" >/dev/null
  "$NEW_RELEASE/.venv/bin/python" -m pip install     --disable-pip-version-check --no-input --retries 4 --timeout 30     "$NEW_RELEASE" >/dev/null
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
  install_launcher

  set -a
  # shellcheck disable=SC1091
  . "$CONFIG_DIR/runtime.env"
  # shellcheck disable=SC1091
  . "$CONFIG_DIR/serverbridge.env"
  if [[ -r "$CONFIG_DIR/network.sh" ]]; then
    # shellcheck disable=SC1091
    . "$CONFIG_DIR/network.sh"
  fi
  set +a

  "$BIN_DIR/tunnel-client" init     --sample sample_mcp_stdio_local     --profile "$PROFILE_NAME"     --profile-dir "$PROFILE_DIR"     --tunnel-id "$TUNNEL_ID"     --mcp-command "$BIN_DIR/launch-mcp"     --health-listen-addr 127.0.0.1:0     --force >/dev/null

  chmod 700 "$PROFILE_DIR"
  chmod 600 "$PROFILE_DIR/$PROFILE_NAME.yaml"

  run_checked "$BIN_DIR/tunnel-client" doctor     --profile-dir "$PROFILE_DIR"     --profile "$PROFILE_NAME"     --explain ||
    die "Tunnel validation failed."

  install_control_cli

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
