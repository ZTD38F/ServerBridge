# Architecture

```text
ChatGPT
   │
   ▼
OpenAI Secure MCP Tunnel
   ▲
   │ outbound HTTPS :443
   │
openai/tunnel-client on VPS
   │
   │ stdio MCP
   ▼
ServerBridge Python MCP server
```

## Why stdio

For a single VPS bridge, stdio avoids:

- local MCP port collisions;
- firewall changes;
- reverse proxies;
- a second HTTP lifecycle;
- accidentally publishing MCP directly to the internet.

The installer asks tunnel-client to use an ephemeral local health/admin port, so even its diagnostics do not require a fixed free port.

## Stdio deployment rule

OpenAI documents that only one active tunnel-client instance should use a given tunnel ID with a stdio MCP binding. ServerBridge therefore installs a single supervised daemon for one deployment.
