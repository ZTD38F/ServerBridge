#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(mktemp -d /tmp/serverbridge-integration.XXXXXX)"
FIXTURES="$ROOT/fixtures"
FAKE_BIN="$ROOT/fake-bin"
INSTALL_ROOT="$ROOT/install"
CONFIG_DIR="$ROOT/config"
STATE_DIR="$ROOT/state"
BIN_DIR="$ROOT/bin"

cleanup() {
  sudo env     SERVERBRIDGE_INSTALL_ROOT="$INSTALL_ROOT"     SERVERBRIDGE_CONFIG_DIR="$CONFIG_DIR"     SERVERBRIDGE_STATE_DIR="$STATE_DIR"     SERVERBRIDGE_BIN_DIR="$BIN_DIR"     bash ./uninstall.sh >/dev/null 2>&1 || true

  sudo rm -f /usr/local/sbin/serverbridgectl
  sudo rm -rf "$CONFIG_DIR"
  rm -rf "$ROOT"
}
trap cleanup EXIT

mkdir -p "$FIXTURES/payload" "$FAKE_BIN"

cat > "$FIXTURES/payload/tunnel-client" <<'FAKE'
#!/usr/bin/env bash
set -Eeuo pipefail

cmd="${1:-}"

case "$cmd" in
  --version)
    echo "tunnel-client v0.0.0-test"
    ;;
  init)
    if [[ "${2:-}" == "--help" || " $* " == *" --help "* ]]; then
      echo "--profile-dir --tunnel-id --mcp-command --health-listen-addr"
      exit 0
    fi

    profile_dir=""
    profile="serverbridge"
    while (($#)); do
      case "$1" in
        --profile-dir) shift; profile_dir="$1" ;;
        --profile) shift; profile="$1" ;;
      esac
      shift || true
    done

    [[ -n "$profile_dir" ]]
    mkdir -p "$profile_dir"
    printf 'profile: %s\n' "$profile" > "$profile_dir/$profile.yaml"
    ;;
  doctor)
    if [[ "${2:-}" == "--help" || " $* " == *" --help "* ]]; then
      echo "--profile-dir --profile --explain"
      exit 0
    fi
    if [[ "${FAKE_DOCTOR_FAIL:-0}" == "1" ]]; then
      echo "intentional doctor failure" >&2
      exit 42
    fi
    echo "doctor ok"
    ;;
  run)
    if [[ "${2:-}" == "--help" || " $* " == *" --help "* ]]; then
      echo "--profile-dir --profile"
      exit 0
    fi
    while :; do sleep 60; done
    ;;
  *)
    echo "unsupported fake tunnel-client command: $*" >&2
    exit 2
    ;;
esac
FAKE
chmod +x "$FIXTURES/payload/tunnel-client"

python - "$FIXTURES" <<'PY'
from pathlib import Path
import zipfile
import sys

root = Path(sys.argv[1])
payload = root / "payload" / "tunnel-client"
archive = root / "tunnel-client-v0.0.0-linux-amd64.zip"

with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    info = zipfile.ZipInfo("tunnel-client")
    info.external_attr = 0o755 << 16
    zf.writestr(info, payload.read_bytes())
PY

(
  cd "$FIXTURES"
  sha256sum tunnel-client-v0.0.0-linux-amd64.zip > SHA256SUMS.txt
)

cat > "$FAKE_BIN/curl" <<'FAKECURL'
#!/usr/bin/env bash
set -Eeuo pipefail

fixtures="${SERVERBRIDGE_TEST_FIXTURES:?}"
out=""
url=""
want_effective=0

while (($#)); do
  case "$1" in
    -o|--output)
      shift
      out="$1"
      ;;
    -w|--write-out)
      shift
      [[ "$1" == *url_effective* ]] && want_effective=1
      ;;
    http://*|https://*)
      url="$1"
      ;;
  esac
  shift
done

if ((want_effective)); then
  printf '%s' 'https://github.com/openai/tunnel-client/releases/tag/v0.0.0'
  exit 0
fi

case "$url" in
  */tunnel-client-v0.0.0-linux-amd64.zip)
    cp "$fixtures/tunnel-client-v0.0.0-linux-amd64.zip" "$out"
    ;;
  */SHA256SUMS.txt)
    cp "$fixtures/SHA256SUMS.txt" "$out"
    ;;
  *)
    # Connectivity probes only.
    [[ -z "$out" ]] || : > "$out"
    ;;
esac
FAKECURL
chmod +x "$FAKE_BIN/curl"

common_env=(
  "PATH=$FAKE_BIN:$PATH"
  "SERVERBRIDGE_TEST_FIXTURES=$FIXTURES"
  "SERVERBRIDGE_SOURCE_DIR=$PWD"
  "SERVERBRIDGE_INSTALL_ROOT=$INSTALL_ROOT"
  "SERVERBRIDGE_CONFIG_DIR=$CONFIG_DIR"
  "SERVERBRIDGE_STATE_DIR=$STATE_DIR"
  "SERVERBRIDGE_BIN_DIR=$BIN_DIR"
  "SERVERBRIDGE_TUNNEL_ID=tunnel_0123456789abcdef"
  "CONTROL_PLANE_API_KEY=sk-test-placeholder"
  "SERVERBRIDGE_TUNNEL_CLIENT_VERSION=v0.0.0"
)

echo "== clean install =="
sudo env "${common_env[@]}" bash ./install.sh --no-start

test -L "$INSTALL_ROOT/current"
test -x "$BIN_DIR/tunnel-client"
test -x /usr/local/sbin/serverbridgectl
test -f "$CONFIG_DIR/runtime.env"
test -f "$CONFIG_DIR/serverbridge.env"
test -f "$CONFIG_DIR/tunnel-client/serverbridge.yaml"

old_current="$(readlink -f "$INSTALL_ROOT/current")"

sudo env "${common_env[@]}" /usr/local/sbin/serverbridgectl doctor >/dev/null

echo "== forced failed update =="
set +e
sudo env "${common_env[@]}" FAKE_DOCTOR_FAIL=1 bash ./install.sh --no-start >/tmp/serverbridge-failed-update.log 2>&1
rc=$?
set -e

if ((rc == 0)); then
  cat /tmp/serverbridge-failed-update.log >&2
  echo "Expected update failure did not occur." >&2
  exit 1
fi

new_current="$(readlink -f "$INSTALL_ROOT/current")"
[[ "$new_current" == "$old_current" ]] || {
  cat /tmp/serverbridge-failed-update.log >&2
  echo "Rollback did not restore the previous current release." >&2
  exit 1
}

sudo env "${common_env[@]}" /usr/local/sbin/serverbridgectl doctor >/dev/null

echo "ServerBridge install + rollback integration test passed."
