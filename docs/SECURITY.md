# Security

ServerBridge is an infrastructure inspection bridge, not a sandbox.

## Runtime secrets

- Runtime API key input is hidden.
- There is no `--api-key` installer argument.
- Runtime configuration is root-readable only.
- The MCP child explicitly drops OpenAI control-plane credentials.
- Process inspection never returns process environment variables.
- Proxy and CA settings are persisted separately in a root-only file.

If a secret appears in a chat, terminal log, screenshot, or shell history, rotate it.

## Network

OpenAI Secure MCP Tunnel uses outbound HTTPS. ServerBridge does not expose a public inbound MCP port.

The installer can preserve common outbound proxy/private-CA environment variables so the service behaves the same after reboot.

## File visibility

The public MCP core is read-only/diagnostic. `SERVERBRIDGE_ALLOWED_ROOTS` controls which filesystem roots can be inspected.

Default:

```text
/
```

For a narrower deployment, edit:

```text
/etc/serverbridge/serverbridge.env
```

then restart:

```bash
sudo serverbridgectl restart
```
