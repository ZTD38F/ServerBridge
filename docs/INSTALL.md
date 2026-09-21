# Installation

## Inputs you need

ServerBridge requires two OpenAI values:

1. `CONTROL_PLANE_TUNNEL_ID` — your `tunnel_...` identifier.
2. `CONTROL_PLANE_API_KEY` — the runtime API key used by `tunnel-client`.

Setup pages:

- https://platform.openai.com/settings/organization/tunnels
- https://platform.openai.com/settings/organization/api-keys
- https://chatgpt.com/#settings/Connectors

## One-line install

```bash
curl -fsSL https://raw.githubusercontent.com/ZTD38F/ServerBridge/main/install.sh | sudo bash
```

The tunnel ID is intentionally visible. The runtime key is read with terminal echo disabled.

## Non-interactive automation

```bash
sudo env \
  SERVERBRIDGE_TUNNEL_ID='tunnel_...' \
  CONTROL_PLANE_API_KEY='...' \
  bash install.sh
```

For normal interactive use, prefer the hidden prompt so the key is not saved in shell history.

## Phases

1. Validate credentials.
2. Detect Linux distribution, architecture, package manager and init system.
3. Install/validate prerequisites.
4. Verify outbound HTTPS.
5. Resolve and checksum-verify the latest stable OpenAI tunnel-client.
6. Prepare an isolated ServerBridge Python release.
7. Create the stdio MCP tunnel profile.
8. Run `tunnel-client doctor --explain`.
9. Configure systemd/OpenRC, start, and verify.

The MCP server is stdio, so no inbound MCP port is opened.
