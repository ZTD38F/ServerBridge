# Installation and operations (v0.5.x)

## Prerequisites

A private Linux VPS with outbound HTTPS, a supported Linux architecture, Python 3.10+, and an OpenAI Secure MCP Tunnel ID plus its runtime API key. The default tested transport pin in the repository is `tunnel-client v0.0.15` (see `TUNNEL_CLIENT_VERSION`); do not automatically assume a newer upstream version is compatible.

Create the tunnel at https://platform.openai.com/settings/organization/tunnels and obtain the runtime key at https://platform.openai.com/settings/organization/api-keys.

## Install a published stable release

```bash
curl -fsSL https://github.com/ZTD38F/ServerBridge/releases/latest/download/bootstrap.sh | sudo bash
```

The interactive installer requests a visible Tunnel ID and a hidden runtime API key. It checks system prerequisites, stages a commit-pinned release and the hash-locked Python runtime, verifies the pinned official OpenAI transport binary, configures an authenticated loopback HTTP supervisor plus an active backend, installs services and the daily update timer, and checks local health.

Do not paste a runtime key in a shell command or share `/etc/serverbridge` credentials. A successfully completed local installation does **not** by itself prove that ChatGPT has discovered the tunnel: open https://chatgpt.com/#settings/Connectors, select the correct tunnel, and scan its tools.

## Check the running installation

```bash
sudo serverbridgectl check
sudo serverbridgectl status
sudo serverbridgectl doctor
sudo serverbridgectl logs 200
systemctl status serverbridge.service serverbridge-supervisor.service
systemctl list-timers serverbridge-update.timer
```

On systemd, the transport service should remain running while ordinary Python backend generations are switched. The local authenticated router uses loopback port 18766; the backend uses 18771 or 18772. Inbound MCP firewall exposure is neither needed nor intended.

## Updates

```bash
sudo serverbridgectl update
```

Auto-update is enabled by default through the systemd timer. A runtime update verifies the released artifact, validates the candidate MCP contract and performs an A/B route switch with recovery and rollback. Active stateful process sessions may postpone an update. Tunnel-client binary upgrades are separate and may require a controlled transport reconnect; always verify the tunnel again in ChatGPT after a transport upgrade.

Do not run `SERVERBRIDGE_CHANNEL=edge` against a production tunnel merely to obtain unreleased code. The stable channel targets an actual published release, not a moving main branch.

To opt out of automatic updates at installation:

```bash
curl -fsSL https://github.com/ZTD38F/ServerBridge/releases/latest/download/bootstrap.sh | sudo bash -s -- --no-auto-update
```

To inspect a local checkout without activation, use `bash ./install.sh --dry-run` with synthetic test values as shown in the repository CI. For production, do not use real keys in a pasted command or log.

## Service managers and recovery

Standard systemd deployment uses `serverbridge.service`, `serverbridge-supervisor.service` and `serverbridge-update.timer`. OpenRC support exists for installation, but the current seamless update engine uses `systemctl`, so do not claim feature-parity for automatic A/B and transport updates on OpenRC without dedicated tests.

On failure, inspect `sudo serverbridgectl check`, `sudo serverbridgectl logs`, `/var/log/serverbridge-update.log` and the non-secret update phase in `/var/lib/serverbridge/update.json`. Avoid restarting a healthy tunnel merely because a backend failed. Preserve the previous release and credentials until rollback and ChatGPT-side MCP tools are independently verified.

See [Architecture](ARCHITECTURE.md), [Security](SECURITY.md), and [Troubleshooting](TROUBLESHOOTING.md).
