# ServerBridge

Connect a private Linux VPS to ChatGPT through **OpenAI Secure MCP Tunnel** — without opening an inbound MCP port.

## Install

You need:

1. Tunnel ID: https://platform.openai.com/settings/organization/tunnels
2. Runtime API key: https://platform.openai.com/settings/organization/api-keys
3. One command:

```bash
curl -fsSL https://raw.githubusercontent.com/ZTD38F/ServerBridge/main/bootstrap.sh | sudo bash
```

The installer asks only for:

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

The public MCP core is read-only/diagnostic. Filesystem reading is intentionally broad by default. ServerBridge only protects its own tunnel/control-plane credential files unless you change `SERVERBRIDGE_PROTECTED_PATHS`.

<details>
<summary><strong>What happens automatically</strong></summary>

- Linux `amd64` / `arm64`
- apt, dnf, yum, apk, pacman, zypper
- systemd / OpenRC
- Python 3.10+
- OpenAI `tunnel-client v0.0.14`, pinned to the tested release
- official SHA-256 verification
- stdio MCP with no fixed MCP port
- hashed Python dependency lock
- outbound proxy/private-CA environment preservation
- isolated releases and rollback
- systemd service hardening
- `tunnel-client doctor`
- service health verification
- CI on Python 3.10/3.12/3.13
- Linux compatibility checks on Ubuntu, Debian, Fedora and Alpine
- dependency vulnerability audit
- daily upstream tunnel-client compatibility monitoring
- release SBOM, checksums and provenance attestation

</details>

Details: [Installation](docs/INSTALL.md) · [Architecture](docs/ARCHITECTURE.md) · [Security](docs/SECURITY.md) · [Troubleshooting](docs/TROUBLESHOOTING.md)

## License

MIT.
