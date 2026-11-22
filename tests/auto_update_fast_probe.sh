#!/usr/bin/env bash
set -Eeuo pipefail
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
mkdir -p "$TEMP/release/.venv/bin" "$TEMP/bin" "$TEMP/state" "$TEMP/fake"
ln -s "$TEMP/release" "$TEMP/current"
printf 'v0.0.15\n' >"$TEMP/release/TUNNEL_CLIENT_VERSION"
printf 'release\n' >"$TEMP/state/supervisor-generation"

cat >"$TEMP/release/.venv/bin/python" <<'FAKEPY'
#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "$1" == "-m" && "$2" == "serverbridge.update_engine" ]]; then
  printf 'updated\n' >>"$MOCK_UPDATED"
elif [[ "$1" == "-c" && "$2" == *"json.load"* ]]; then
  printf '%s\n' "$MOCK_PHASE"
elif [[ "$1" == "-c" ]]; then
  printf 'v0.5.13\n'
else
  exit 9
fi
FAKEPY
chmod +x "$TEMP/release/.venv/bin/python"

cat >"$TEMP/bin/tunnel-client" <<'FAKECLI'
#!/usr/bin/env bash
printf '%s\n' '0.0.15+test'
FAKECLI
chmod +x "$TEMP/bin/tunnel-client"

cat >"$TEMP/fake/curl" <<'FAKECURL'
#!/usr/bin/env bash
printf '%s' "$MOCK_RELEASE_URL"
FAKECURL
chmod +x "$TEMP/fake/curl"

export SERVERBRIDGE_INSTALL_ROOT="$TEMP"
export SERVERBRIDGE_STATE_DIR="$TEMP/state"
export SERVERBRIDGE_BIN_DIR="$TEMP/bin"
export SERVERBRIDGE_UPDATE_LOG="$TEMP/updates.log"
export MOCK_UPDATED="$TEMP/updated"
export MOCK_PHASE=COMMITTED
export PATH="$TEMP/fake:$PATH"

export MOCK_RELEASE_URL=https://github.com/ZTD38F/ServerBridge/releases/tag/v0.5.13
bash ./auto-update.sh
[[ ! -e "$MOCK_UPDATED" ]] || { echo "Unchanged release ran updater" >&2; exit 1; }

export MOCK_RELEASE_URL=https://github.com/ZTD38F/ServerBridge/releases/tag/v0.5.14
bash ./auto-update.sh
[[ "$(wc -l <"$MOCK_UPDATED")" == 1 ]] || { echo "Changed release did not invoke updater" >&2; exit 1; }

export MOCK_RELEASE_URL=https://github.com/ZTD38F/ServerBridge/releases/tag/v0.5.13
printf 'wrong-generation\n' >"$TEMP/state/supervisor-generation"
bash ./auto-update.sh
[[ "$(wc -l <"$MOCK_UPDATED")" == 2 ]] || { echo "Stale supervisor bypassed updater" >&2; exit 1; }

printf 'release\n' >"$TEMP/state/supervisor-generation"
echo '{"phase":"FAILED_ROLLED_BACK"}' >"$TEMP/state/update.json"
export MOCK_PHASE=FAILED_ROLLED_BACK
bash ./auto-update.sh
[[ "$(wc -l <"$MOCK_UPDATED")" == 3 ]] || { echo "Failed transaction was skipped" >&2; exit 1; }

export MOCK_PHASE=COMMITTED
echo '{"phase":"COMMITTED"}' >"$TEMP/state/update.json"
bash ./auto-update.sh
[[ "$(wc -l <"$MOCK_UPDATED")" == 3 ]] || { echo "Clean steady-state failed" >&2; exit 1; }

printf 'v9.9.9\n' >"$TEMP/release/TUNNEL_CLIENT_VERSION"
bash ./auto-update.sh
[[ "$(wc -l <"$MOCK_UPDATED")" == 4 ]] || { echo "Transport mismatch was skipped" >&2; exit 1; }

grep -Fq 'OnUnitInactiveSec=30s' packaging/serverbridge-update.timer
grep -Fq 'AccuracySec=1s' packaging/serverbridge-update.timer
echo "Fast release probe and 30-second timer contracts passed"
