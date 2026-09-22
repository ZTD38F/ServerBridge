# Installation

## Before you start

Create:

- Tunnel ID: https://platform.openai.com/settings/organization/tunnels
- Runtime API key: https://platform.openai.com/settings/organization/api-keys

Then run:

```bash
curl -fsSL https://raw.githubusercontent.com/ZTD38F/ServerBridge/main/bootstrap.sh | sudo bash
```

The bootstrap pins one Git commit before downloading the installer, so one installation cannot accidentally mix files from two different repository states.

The installer asks only for the tunnel ID and runtime key. The tunnel ID is visible; the runtime key is hidden.

## What happens automatically

1. Check Linux, architecture, resources and prerequisites.
2. Check outbound HTTPS.
3. Install the tested OpenAI `tunnel-client v0.0.14` and verify its official SHA-256.
4. Install Python runtime dependencies from the hashed `requirements.lock`.
5. Prepare an isolated ServerBridge release.
6. Create the stdio tunnel profile and autostart service.
7. Run `doctor`, then start and verify the service.

No inbound MCP port is opened.

## Check

```bash
sudo serverbridgectl check
```

More detail:

```bash
sudo serverbridgectl status
sudo serverbridgectl doctor
sudo serverbridgectl logs 200
```

## Dry-run

From a clone:

```bash
sudo SERVERBRIDGE_TUNNEL_ID=tunnel_example \
  CONTROL_PLANE_API_KEY=sk-test-placeholder \
  ./install.sh --dry-run
```

A local checkout is used as the source tree; the installer does not silently replace it with `main`.

## Proxies and private CA

Common proxy and tunnel-client CA variables are preserved into root-only service environment files so the long-running service behaves like the installer session.

## Advanced overrides

Use only when intentionally testing:

```bash
SERVERBRIDGE_TUNNEL_CLIENT_VERSION=v0.0.14
SERVERBRIDGE_ALLOWED_ROOTS=/
SERVERBRIDGE_PROTECTED_PATHS=/etc/serverbridge/runtime.env
```

The tested tunnel-client version is pinned by default. The daily upstream workflow reports compatibility with newer OpenAI releases before the pin is changed.
