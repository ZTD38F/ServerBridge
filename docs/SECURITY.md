# Security

ServerBridge is an infrastructure inspection bridge, not a sandbox.

## Read model

The public MCP core is read-only/diagnostic, but filesystem reading is intentionally broad by default because ServerBridge is designed as a universal server inspector.

ServerBridge protects only its own control-plane credential/configuration paths by default:

- runtime API key file;
- preserved network environment;
- tunnel-client profile directory.

Change `SERVERBRIDGE_PROTECTED_PATHS` if you want a narrower or completely unrestricted read model.

## Runtime secrets

- Runtime API key input is hidden.
- There is no `--api-key` CLI option.
- Runtime configuration is root-readable only.
- The MCP child explicitly drops OpenAI control-plane credentials.
- Process inspection does not return process environment variables.

## Network

The tunnel uses outbound HTTPS. ServerBridge exposes no inbound MCP port.

## systemd hardening

The generated unit uses conservative hardening that does not remove broad server read access:

- `NoNewPrivileges`
- private temporary directory and devices
- kernel/module/control-group write protections
- SUID/SGID restrictions
- strict service umask

These controls reduce accidental privilege escalation while preserving ServerBridge's inspection purpose.

## Supply chain

- tunnel-client is pinned to the tested release and verified with OpenAI's published SHA-256 manifest;
- Python runtime dependencies are fully locked with hashes;
- GitHub Actions are pinned to commit SHAs;
- CI runs dependency vulnerability auditing;
- releases publish checksums, CycloneDX SBOM and provenance attestations.
