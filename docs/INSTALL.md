# Installation

## Before you start

Create:

- Tunnel ID: https://platform.openai.com/settings/organization/tunnels
- Runtime API key: https://platform.openai.com/settings/organization/api-keys

Then run:

```bash
curl -fsSL https://raw.githubusercontent.com/ZTD38F/ServerBridge/main/install.sh | sudo bash
```

The installer asks only for the tunnel ID and runtime key.

The tunnel ID is visible while typing. The runtime key is hidden.

## What happens automatically

ServerBridge:

1. Checks the Linux host and dependencies.
2. Verifies network access.
3. Downloads the latest stable official `openai/tunnel-client` and checks SHA-256.
4. Installs ServerBridge into an isolated release directory.
5. Creates the stdio tunnel profile and autostart service.
6. Runs `doctor`, starts the service, and verifies it stays healthy.

No inbound MCP port is opened.

## Check the installation

```bash
sudo serverbridgectl check
```

For more detail:

```bash
sudo serverbridgectl status
sudo serverbridgectl doctor
sudo serverbridgectl logs 200
```

## Dry-run

```bash
sudo SERVERBRIDGE_TUNNEL_ID=tunnel_example \
  CONTROL_PLANE_API_KEY=sk-test-placeholder \
  ./install.sh --dry-run
```

## Proxies and private CA

If the installer is started with standard proxy variables such as `HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY`, or tunnel-client CA variables, ServerBridge preserves them in a root-only network environment file for the long-running service.

## Non-interactive installation

```bash
sudo env \
  SERVERBRIDGE_TUNNEL_ID='tunnel_...' \
  CONTROL_PLANE_API_KEY='...' \
  bash install.sh
```

For normal use, the interactive hidden key prompt is preferable because it avoids placing the key directly in shell history.
