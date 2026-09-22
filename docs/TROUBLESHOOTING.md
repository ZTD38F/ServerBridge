# Troubleshooting

Start here:

```bash
sudo serverbridgectl check
```

If it fails:

```bash
sudo serverbridgectl doctor
sudo serverbridgectl logs 200
```

## Tunnel not visible in ChatGPT

Check that:

- ServerBridge is running;
- the tunnel is associated with the correct ChatGPT workspace/account;
- your OpenAI principal has Tunnels Read + Use.

Then open:

https://chatgpt.com/#settings/Connectors

## Runtime key problem

Create a runtime API key:

https://platform.openai.com/settings/organization/api-keys

Then rerun the installer.

## Network problem

The VPS needs working DNS and outbound HTTPS (TCP 443) to OpenAI, GitHub and PyPI.

ServerBridge preserves common proxy environment variables during installation.

## Python is too old

Python 3.10+ is required. ServerBridge stops before activation instead of compiling an arbitrary Python version from source.

## Existing ServerBridge path is rejected

This is deliberate. The installer refuses to overwrite directories or service files that are not marked as ServerBridge-managed.

## No systemd or OpenRC

The app can still be prepared and validated, but ServerBridge does not claim automatic 24/7 supervision on an unknown init system.
