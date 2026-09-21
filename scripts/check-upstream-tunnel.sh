#!/usr/bin/env bash
set -Eeuo pipefail

TMP="$(mktemp -d /tmp/serverbridge-upstream.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

latest="$(curl -fsSL -o /dev/null -w '%{url_effective}'   https://github.com/openai/tunnel-client/releases/latest)"
tag="${latest##*/}"

[[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
  echo "Could not resolve a stable tunnel-client tag: $tag" >&2
  exit 1
}

base="https://github.com/openai/tunnel-client/releases/download/$tag"
curl -fsSL --retry 4 "$base/SHA256SUMS.txt" -o "$TMP/SHA256SUMS.txt"

for arch in amd64 arm64; do
  asset="tunnel-client-${tag}-linux-${arch}.zip"
  curl -fL --retry 4 "$base/$asset" -o "$TMP/$asset"

  grep -E "[[:space:]]${asset//./\\.}$" "$TMP/SHA256SUMS.txt" > "$TMP/$asset.sha256"
  (
    cd "$TMP"
    sha256sum -c "$asset.sha256"
  )

  mkdir "$TMP/$arch"
  unzip -q "$TMP/$asset" -d "$TMP/$arch"
  binary="$(find "$TMP/$arch" -type f -name tunnel-client -print -quit)"
  [[ -n "$binary" ]] || {
    echo "No tunnel-client binary in $asset" >&2
    exit 1
  }

  chmod +x "$binary"

  # Only execute the native runner architecture.
  if [[ "$arch" == "amd64" && "$(uname -m)" =~ ^(x86_64|amd64)$ ]] ||
     [[ "$arch" == "arm64" && "$(uname -m)" =~ ^(aarch64|arm64)$ ]]; then
    init_help="$("$binary" init --help 2>&1)"
    doctor_help="$("$binary" doctor --help 2>&1)"
    run_help="$("$binary" run --help 2>&1)"

    for flag in --profile-dir --tunnel-id --mcp-command --health-listen-addr; do
      grep -Fq -- "$flag" <<<"$init_help"
    done
    grep -Fq -- "--profile-dir" <<<"$doctor_help"
    grep -Fq -- "--profile-dir" <<<"$run_help"
  fi
done

echo "OpenAI tunnel-client $tag remains compatible with ServerBridge."
