# Changelog

## Unreleased

- Forward partial HTTP and SSE response chunks immediately through the authenticated supervisor rather than buffering until 64 KiB or EOF, preserving real-time streams.
- Add actual one-line piped-bootstrap PTY regressions for Enter-to-reuse, replacement and fresh install with synthetic credentials, plus streaming E2E coverage.
- Correct installation documentation for the existing 30-second timer and default access mode.
- Eliminate a narrow credential echo race by disabling terminal echo before showing the API-key prompt, and restore the previous terminal state on successful and interrupted reads.

## 0.5.16 — 2026-11-22

- Nonfunctional deployment canary to verify a previously updated server discovers and installs the next stable release by the native timer without a manual invocation; no runtime tool schemas or security settings changed.
- Retain updater-component reconciliation, 30-second timer, private semantic overlay hook and rollback guarantees.

## 0.5.15 — 2026-11-22

- Self-update the update launcher and systemd timer after stable A/B releases, preserving custom wrappers and per-host rollback.
- Repair updater drift on already-current releases; respect disabled schedules and preserve local semantic tool overlays.
- Record verified component SHA-256 receipts and guard abnormal custom launcher replacement.

## 0.5.14 — 2026-11-22

- The ordinary one-line bootstrap independently asks whether to reuse saved Tunnel ID and runtime API key, with Enter meaning yes.
- Declining either saved value prompts only for that replacement. A new install prompts for missing credentials, and a noninteractive upgrade reuses both.
- Preserve explicit environment/argument overrides, secret input redaction and all existing configuration/rollback behavior.
- Add interactive default, replacement, first-install, noninteractive and negative tests.

## 0.5.13 — 2026-11-22

- Enable Full Access as the default on owner-managed private tunnel installs and reinstalls; explicit read-only overrides remain available.
- Replace the delayed daily update timer with a 30-second monotonic check; use a lightweight public release redirect probe on steady state to avoid GitHub API rate limits.
- Keep checksummed stable release activation, A/B health checks, lock, preserved credentials and rollback protections.

## 0.5.12 — 2026-11-22

- Correct modern-install upgrade credential reuse: read the existing runtime API key only from the managed, non-symlink protected file without printing it.
- Test read-only to full-access upgrade while the runtime API key environment variable is absent.

## 0.5.11 — 2026-11-22

- Offer interactive Full Access through the ordinary stable installer, while preserving the existing mode on unattended upgrades.
- Add full-access and read-only modes that persist and normalize exec/write/process/service control, including upgrades from read-only.
- Verify real installed runtime flags before reporting successful installation.
- Extend installer mode tests and retain private-tunnel authentication, credentials protection and rollback behavior.

## 0.5.10 — 2026-11-16

- Revalidate cached release source files against the checksum-verified published archive before reuse; reject drift without replacing a potentially active generation.
- Stop and record a failed pre-switch candidate if MCP tool negotiation or candidate health validation fails.
- Make concurrent process-session admission atomic and report ring-buffer truncation with absolute output cursors.
- Add real local HTTP routing/authorization/drain tests, authentic MCP initialize/tools-list/tools-call E2E and failure-injection regressions.
- Patch the locked `opentelemetry-api` dependency to 1.45.2 to address CVE-2026-126360, preserving hash-based installation.
- Update the architecture and installation documentation to match the actual supervisor + Streamable HTTP design.

## 0.5.9 — 2026-10-29

- Preserve the transport while updating the supervisor.
- Reject zombie backend PIDs and sanitize updater failure metadata.
- [Release notes](https://github.com/ZTD38F/ServerBridge/releases/tag/v0.5.9).

## 0.5.8 — 2026-10-29

- Redact credentials embedded in nested mutation-audit structures.
- [Release notes](https://github.com/ZTD38F/ServerBridge/releases/tag/v0.5.8).

## 0.5.7 — 2026-10-16

- Improve tool descriptions and MCP discoverability.
- [Release notes](https://github.com/ZTD38F/ServerBridge/releases/tag/v0.5.7).

## 0.5.6 — 2026-10-09

- Correct the recorded current-generation metadata after successful promotion.
- [Release notes](https://github.com/ZTD38F/ServerBridge/releases/tag/v0.5.6).

## 0.5.5 — 2026-10-06

- Synchronize package, runtime and plugin version metadata.
- [Release notes](https://github.com/ZTD38F/ServerBridge/releases/tag/v0.5.5).

## 0.5.4 — 2026-10-06

- Repair updater reconciliation and transport version normalization.
- [Release notes](https://github.com/ZTD38F/ServerBridge/releases/tag/v0.5.4).

## 0.5.3 — 2026-10-06

- Restore an unhealthy or dead backend through the supervisor watchdog.
- [Release notes](https://github.com/ZTD38F/ServerBridge/releases/tag/v0.5.3).

## 0.5.2 — 2026-10-04

- Prevent self-hosted updater deadlock while draining an active MCP request.
- [Release notes](https://github.com/ZTD38F/ServerBridge/releases/tag/v0.5.2).

## 0.5.1 — 2026-10-04

- Restore the Browser Live MCP adapter.
- [Release notes](https://github.com/ZTD38F/ServerBridge/releases/tag/v0.5.1).

## 0.5.0 — 2026-10-03

- Introduce generation-based Streamable HTTP MCP updates, stable supervisor routing, automatic recovery and rollback.
- [Release notes](https://github.com/ZTD38F/ServerBridge/releases/tag/v0.5.0).

## 0.4.0 — 2026-09-25

Remote-operations release:

- added bounded line-based `read_file` with offset/tail pagination and `file_stat`;
- fixed `list_files(include_hidden=...)`;
- added typed `search_files` and `search_text`;
- added opt-in atomic `write_file`, hash-guarded `edit_file`, and `move_file`;
- added persistent process sessions with stdin, incremental output, session listing and termination;
- added typed service start/stop/restart controls;
- added `listening_ports`, `tcp_probe`, and `http_probe` diagnostics;
- expanded process metadata with thread count, start time and elapsed time;
- added capability flags for write/process/service control, defaulting to execution mode for backward compatibility;
- added append-only best-effort mutation audit logging and secret redaction for command/process output;
- split reusable security/path/session logic out of the MCP registration layer;
- expanded MCP and security smoke tests for the new operations.

## 0.2.1 — 2026-09-22

Stable-channel patch:

- made the default bootstrap resolve the latest published GitHub Release instead of unreleased `main`;
- retained an explicit `SERVERBRIDGE_CHANNEL=edge` mode for development testing;
- made `update.sh` route through the same stable bootstrap;
- added `sudo serverbridgectl update`;
- added mocked regression tests for stable/edge resolution and generated update CLI behavior;
- kept each install pinned to one exact commit SHA.

## 0.2.0 — 2026-09-22

Reliability, portability and release-engineering release:

- reduced installer UI from nine stages to five;
- added one-command commit-pinned bootstrap;
- added `serverbridgectl check`;
- suppressed successful diagnostic noise while preserving failure detail;
- added early transactional rollback and restoration of previous service state;
- added real clean-install → failed-update → rollback integration testing;
- pinned the tested OpenAI `tunnel-client` to v0.0.14;
- retained a daily compatibility check against future tunnel-client releases;
- added SHA-256 verification and tunnel-client CLI compatibility preflight;
- pinned the full Python runtime dependency graph with hashes from the Python 3.10 baseline;
- added Python 3.10 / 3.12 / 3.13 protocol tests;
- added Ubuntu 24.04, Debian 12, Fedora and Alpine compatibility jobs;
- added `pip-audit` dependency vulnerability checking;
- pinned GitHub Actions to immutable commit SHAs;
- added automatic release archives, SHA256SUMS, CycloneDX SBOM and build-provenance attestation;
- added apt/dpkg lock waiting, download retries and basic disk/RAM preflight;
- preserved common proxy/private-CA settings for the long-running service;
- made proxy persistence safe for both systemd and shell sourcing;
- added conservative systemd hardening without removing broad inspection access;
- made filesystem reading bounded and large-file hashing capped;
- made process inspection portable through Linux `/proc` without exposing argv/environment;
- added OpenRC-aware service inspection;
- kept broad server file inspection by default while protecting ServerBridge's own control-plane credentials;
- added Dependabot monitoring for Python and GitHub Actions;
- aligned README, plugin metadata, security docs and contribution workflow with the actual read-only public core.

## 0.1.0 — 2026-09-21

Initial public design:

- visible tunnel-ID prompt;
- hidden runtime-key prompt;
- Linux amd64/arm64 detection;
- common package-manager support;
- systemd/OpenRC integration;
- checksum-verified OpenAI tunnel-client download;
- stdio MCP transport;
- isolated releases and rollback;
- read-only diagnostic MCP tools;
- plugin metadata, skill and CI.
