# ServerBridge

Connect a private Linux VPS to ChatGPT through **OpenAI Secure MCP Tunnel** — without opening an inbound MCP port.

> ServerBridge's public core is read-only/diagnostic. Treat server access as sensitive infrastructure access.

## Install

You need only:

1. A **Tunnel ID**: https://platform.openai.com/settings/organization/tunnels
2. A **Runtime API key**: https://platform.openai.com/settings/organization/api-keys
3. This command:

```bash
curl -fsSL https://raw.githubusercontent.com/ZTD38F/ServerBridge/main/install.sh | sudo bash
```

The installer asks:

```text
Tunnel ID: tunnel_...
Runtime API key: ********
```

When it says **ServerBridge is ready**, open:

https://chatgpt.com/#settings/Connectors

Choose your tunnel and scan the MCP tools.

## Useful commands

```bash
sudo serverbridgectl check
sudo serverbridgectl logs
sudo serverbridgectl restart
```

Update:

```bash
curl -fsSL https://raw.githubusercontent.com/ZTD38F/ServerBridge/main/update.sh | sudo bash
```

Uninstall:

```bash
curl -fsSL https://raw.githubusercontent.com/ZTD38F/ServerBridge/main/uninstall.sh | sudo bash
```

## Built-in tools

`server_info` · `list_files` · `read_text` · `service_status` · `service_logs` · `process_list`

<details>
<summary><strong>What the installer handles automatically</strong></summary>

- Linux `amd64` / `arm64`
- apt, dnf, yum, apk, pacman, zypper
- systemd / OpenRC
- Python 3.10+
- latest stable official `openai/tunnel-client`
- SHA-256 verification
- stdio MCP with no fixed MCP port
- outbound proxy environment preservation
- isolated releases
- rollback after failed activation
- root-only credentials
- MCP secret-environment isolation
- `tunnel-client doctor`
- service health verification

</details>

For details: [Installation](docs/INSTALL.md) · [Architecture](docs/ARCHITECTURE.md) · [Security](docs/SECURITY.md) · [Troubleshooting](docs/TROUBLESHOOTING.md)

## License

MIT.
