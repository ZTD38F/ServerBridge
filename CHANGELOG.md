# Changelog

## 0.2.0 — 2026-09-21

Reliability and UX release:

- reduced the installer UI from nine stages to five;
- simplified README and post-install instructions;
- added `serverbridgectl check`;
- hidden successful `doctor` verbosity while preserving failure diagnostics;
- activated rollback before the first ServerBridge filesystem mutation;
- expanded rollback to network/proxy config and management markers;
- added foreign config/state collision protection;
- preserved common proxy/private-CA environment settings for the service;
- added pip retry/timeout handling;
- added a real MCP protocol smoke test in CI;
- added installer dry-run CI coverage;
- aligned plugin metadata with the read-only public core.

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
