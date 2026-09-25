# Security

ServerBridge is an infrastructure inspection bridge, not a sandbox.

## Read model

The public MCP core is read-only/diagnostic, but filesystem reading is intentionally broad by default because ServerBridge is designed as a universal server inspector.

ServerBridge protects only its own control-plane credential/configuration paths by default:

- runtime API key file;
- preserved network environment;
- tunnel-client profile directory.

Change `SERVERBRIDGE_PROTECTED_PATHS` if you want a narrower or completely unrestricted read model.

## Optional mutation capabilities

`run_command` is not registered unless `SERVERBRIDGE_ENABLE_EXEC=1` (or an equivalent explicit true value) is persisted. When enabled, it executes with the OS privileges of ServerBridge; the default systemd service runs as root.

Typed mutation families can also be controlled independently with `SERVERBRIDGE_ENABLE_WRITE`, `SERVERBRIDGE_ENABLE_PROCESS`, and `SERVERBRIDGE_ENABLE_SERVICE_CONTROL`. For backward compatibility, each defaults to the value of `SERVERBRIDGE_ENABLE_EXEC` when not explicitly set. Filesystem writes are atomic and `edit_file` can require an expected SHA-256 to detect concurrent changes. Mutation operations are written to a best-effort append-only audit log (default `/var/lib/serverbridge/audit.jsonl`), while command and persistent-process output passes through secret redaction before returning through MCP.

Execution mode therefore changes the trust model substantially. It is intended only for a private tunnel whose operator explicitly wants remote administration. The tool accepts argv-form commands, has bounded output, enforces a configured timeout, terminates the whole process group on timeout, and does not echo full command arguments in its response. The file-tool protected-path boundary does **not** sandbox an enabled root command.

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
