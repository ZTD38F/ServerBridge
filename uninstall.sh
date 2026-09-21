#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_ROOT="${SERVERBRIDGE_INSTALL_ROOT:-/opt/serverbridge}"
CONFIG_DIR="${SERVERBRIDGE_CONFIG_DIR:-/etc/serverbridge}"
STATE_DIR="${SERVERBRIDGE_STATE_DIR:-/var/lib/serverbridge}"
BIN_DIR="${SERVERBRIDGE_BIN_DIR:-/usr/local/lib/serverbridge}"

[[ ${EUID:-$(id -u)} -eq 0 ]] || {
  echo "Run as root/sudo." >&2
  exit 1
}

[[ -e "$INSTALL_ROOT/.serverbridge-managed" ]] || {
  echo "$INSTALL_ROOT is not marked as ServerBridge-managed; refusing destructive removal." >&2
  exit 1
}

if command -v systemctl >/dev/null 2>&1 && [[ -f /etc/systemd/system/serverbridge.service ]]; then
  systemctl disable --now serverbridge.service >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/serverbridge.service
  systemctl daemon-reload || true
fi

if command -v rc-service >/dev/null 2>&1 && [[ -f /etc/init.d/serverbridge ]]; then
  rc-service serverbridge stop >/dev/null 2>&1 || true
  rc-update del serverbridge default >/dev/null 2>&1 || true
  rm -f /etc/init.d/serverbridge
fi

rm -f /usr/local/sbin/serverbridgectl
rm -rf "$INSTALL_ROOT" "$STATE_DIR" "$BIN_DIR"

cat <<EOF
ServerBridge program files were removed.

For safety, credentials/configuration were NOT deleted:
  $CONFIG_DIR

Review them first, then remove manually if desired:
  sudo rm -rf '$CONFIG_DIR'

The remote OpenAI tunnel itself was NOT deleted.
EOF
