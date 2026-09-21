# Troubleshooting

Start with:

```bash
sudo serverbridgectl doctor
sudo serverbridgectl status
sudo serverbridgectl logs 200
```

## Runtime key is missing

Create a runtime API key at:

https://platform.openai.com/settings/organization/api-keys

Then rerun the installer.

## Cannot reach OpenAI/GitHub/PyPI

The VPS needs working DNS, CA certificates, and outbound TCP 443.

## Python is older than 3.10

ServerBridge stops instead of compiling an arbitrary Python version from source. Upgrade the OS/Python source and rerun.

## No systemd/OpenRC

Installation can prepare the app/profile, but ServerBridge will explicitly report that automatic 24/7 supervision could not be configured.

## Existing /opt/serverbridge is rejected

The installer only manages that directory when the ServerBridge marker exists. This prevents accidental replacement of an unrelated application.
