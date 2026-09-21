# ServerBridge

**ServerBridge** turns a Linux VPS into a private MCP backend for ChatGPT through the official OpenAI Secure MCP Tunnel.

The installer is designed for predictable server setup: it performs preflight checks, asks for the visible `tunnel_id`, accepts the runtime API key with hidden input, installs a verified OpenAI `tunnel-client`, creates an isolated Python environment, configures autostart, runs `doctor`, starts the bridge, and verifies the service.

> [!WARNING]
> ServerBridge exposes powerful server-administration tools. Treat a connected bridge like root SSH access. Use it only on systems you own or administer.

## Quick start

1. Create or inspect a tunnel: https://platform.openai.com/settings/organization/tunnels
2. Create a runtime API key: https://platform.openai.com/settings/organization/api-keys
3. Install:

```bash
curl -fsSL https://raw.githubusercontent.com/ZTD38F/ServerBridge/main/install.sh | sudo bash
```

The installer asks for:

```text
Tunnel ID (visible): tunnel_...
Runtime API key (hidden):
```

Then open https://chatgpt.com/#settings/Connectors and scan/refresh the tunnel-backed MCP tools.

## Reliability goals

- Linux `amd64` and `arm64`.
- apt, dnf, yum, apk, pacman and zypper detection.
- systemd and OpenRC integration.
- stdio MCP: no local MCP TCP port or reverse proxy.
- latest stable official `openai/tunnel-client`.
- SHA-256 verification against official release checksums.
- isolated releases and rollback on failed activation.
- root-only runtime configuration.
- MCP child does not inherit OpenAI control-plane secrets.
- `tunnel-client doctor --explain` before success.
- no inbound VPS port required.

## Safe preview

```bash
git clone https://github.com/ZTD38F/ServerBridge.git
cd ServerBridge
sudo SERVERBRIDGE_TUNNEL_ID=tunnel_example CONTROL_PLANE_API_KEY=dry-run ./install.sh --dry-run
```

## Management

```bash
sudo serverbridgectl status
sudo serverbridgectl doctor
sudo serverbridgectl logs
sudo serverbridgectl restart
sudo serverbridgectl stop
```

## Update

```bash
curl -fsSL https://raw.githubusercontent.com/ZTD38F/ServerBridge/main/update.sh | sudo bash
```

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/ZTD38F/ServerBridge/main/uninstall.sh | sudo bash
```

The uninstaller deliberately preserves `/etc/serverbridge` and never deletes the remote OpenAI tunnel.

## Built-in MCP tools

`server_info`, `list_files`, `read_text`, `write_text`, `run_command`, `service_status`, `service_action`, `service_logs`, `process_list`.

See the files in `docs/` for installation, architecture, security and troubleshooting details.

## Google and other integrations

ServerBridge is the transport/backend foundation. Google OAuth credentials cannot be inferred from an OpenAI tunnel ID, so the base installer never asks for Google passwords or invents account tokens.

## License

MIT.
