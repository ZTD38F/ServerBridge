# Changelog

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
