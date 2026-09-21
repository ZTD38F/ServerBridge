# Security

ServerBridge is an administration bridge, not a sandbox.

## Trust model

Treat access to the connected MCP app like privileged server access. Keep the tunnel private to the intended account/workspace.

## Runtime secrets

- Runtime API key input is hidden.
- There is no `--api-key` installer argument.
- Protected config is root-readable only.
- The MCP child launcher unsets OpenAI control-plane secrets before starting Python.
- Built-in process inspection does not expose process environments.

If a secret is ever printed into a chat, log, shell history, or screenshot, rotate it.

## Network

OpenAI Secure MCP Tunnel uses outbound HTTPS. ServerBridge itself does not require a public inbound MCP port.

## File scope

The MCP core uses `SERVERBRIDGE_ALLOWED_ROOTS`. The default is `/` for a universal server inspector. Restrict it in `/etc/serverbridge/serverbridge.env` when broad filesystem visibility is not required.
