#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(mktemp -d /tmp/serverbridge-bootstrap-test.XXXXXX)"
trap 'rm -rf "$ROOT"' EXIT

mkdir -p "$ROOT/bin"

cat > "$ROOT/bin/curl" <<'MOCK'
#!/usr/bin/env bash
set -Eeuo pipefail

out=""
url=""

while (($#)); do
  case "$1" in
    -o|--output)
      shift
      out="$1"
      ;;
    http://*|https://*)
      url="$1"
      ;;
  esac
  shift
done

stable_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
edge_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

case "$url" in
  */releases/latest)
    printf '{"tag_name":"v9.8.7"}'
    ;;
  */commits/v9.8.7)
    printf '{"sha":"%s"}' "$stable_sha"
    ;;
  */commits/main)
    printf '{"sha":"%s"}' "$edge_sha"
    ;;
  */raw.githubusercontent.com/*|https://raw.githubusercontent.com/*)
    [[ -n "$out" ]]
    cat > "$out" <<'DOWNLOADED'
#!/usr/bin/env bash
printf 'installer-sha=%s\n' "$SERVERBRIDGE_SOURCE_SHA"
printf 'installer-args=%s\n' "$*"
DOWNLOADED
    ;;
  *)
    printf 'unexpected URL: %s\n' "$url" >&2
    exit 70
    ;;
esac
MOCK
chmod +x "$ROOT/bin/curl"

stable="$(
  PATH="$ROOT/bin:$PATH" TMPDIR="$ROOT"     bash ./bootstrap.sh alpha beta
)"

grep -Fq 'ServerBridge v9.8.7' <<<"$stable"
grep -Fq 'installer-sha=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' <<<"$stable"
grep -Fq 'installer-args=alpha beta' <<<"$stable"

edge="$(
  PATH="$ROOT/bin:$PATH" TMPDIR="$ROOT" SERVERBRIDGE_CHANNEL=edge     bash ./bootstrap.sh gamma
)"

grep -Fq 'ServerBridge edge (bbbbbbbbbbbb)' <<<"$edge"
grep -Fq 'installer-sha=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' <<<"$edge"
grep -Fq 'installer-args=gamma' <<<"$edge"

if PATH="$ROOT/bin:$PATH" TMPDIR="$ROOT" SERVERBRIDGE_CHANNEL=invalid   bash ./bootstrap.sh >/dev/null 2>&1; then
  echo "invalid channel unexpectedly succeeded" >&2
  exit 1
fi

echo "bootstrap channel tests passed"
