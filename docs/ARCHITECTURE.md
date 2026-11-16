# Architecture (v0.5.x)

ServerBridge keeps one OpenAI Secure MCP Tunnel connection and routes local MCP requests to one of two independently replaceable Python backend generations.

```text
ChatGPT
  |
OpenAI Secure MCP Tunnel (outbound HTTPS 443; no inbound MCP port)
  |
tunnel-client  [serverbridge.service, long-lived]
  | authenticated HTTP 127.0.0.1:18766/mcp
  v
Supervisor/router [serverbridge-supervisor.service, long-lived]
  | authenticated HTTP
  +--> active Python MCP backend 127.0.0.1:18771
  +--> candidate Python MCP backend 127.0.0.1:18772
```

Both local HTTP hops use separate root-owned token files. The stable supervisor routes requests using `/var/lib/serverbridge/route.json` and tracks in-flight requests per generation. The tunnel transport is independent of backend restarts. The supervisor watchdog recovers a failed active backend. `serverbridge.service` is ordered after, but must not require the supervisor to remain active in order to preserve the transport across supervisor updates.

## Update lifecycle

`serverbridge.update_engine` obtains an exclusive update lock, resolves the latest *published stable* GitHub release, verifies the release archive against SHA256SUMS, validates any already-installed copy against the verified source files, and stages a new immutable generation. The source runtime is installed with hash-locked Python dependencies. It starts a candidate backend on the inactive loopback port and checks health and the MCP tool schemas before switching the route.

On successful promotion, the updater drains existing requests, observes candidate health, updates `current` and `previous` symlinks, and retires the old backend. Active persistent process sessions defer promotion rather than being silently orphaned. The journal `/var/lib/serverbridge/update.json` records transaction phases for recovery. Failed candidates are stopped and the previous route remains or is restored.

An ordinary **RUNTIME_UPDATE** should not restart the tunnel process. A **SUPERVISOR_UPDATE** may restart the supervisor without intentionally restarting the tunnel. A **TRANSPORT_UPDATE** is a different operation: if the tested tunnel-client binary changes, a short controlled reconnection is required, with rollback on failure. Never run two transport clients for one tunnel ID unless upstream explicitly supports it.

## Deployment limitations

The currently implemented seamless-update CLI uses `systemctl` for supervisor/transport updates; the installed service manager is therefore part of the seamless-update support contract. Check platform capabilities before treating OpenRC and systemd as identical. Optional site-specific MCP extensions may add tools not present in the public repository: tool-contract validation deliberately rejects a candidate that would remove them.

See [Installation](INSTALL.md), [Security](SECURITY.md), and [Troubleshooting](TROUBLESHOOTING.md).
