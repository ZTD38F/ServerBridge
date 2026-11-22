# ServerBridge fleet update contract

This document is operational guidance. A published release does not prove that
every installed server received it. Do not expose credentials or per-host
machine identifiers in the public repository.

## All update surfaces

| Surface | Desired behavior | Evidence |
| --- | --- | --- |
| GitHub main / Release | Green CI, verified checksum, SBOM, stable tag | CI, Release checks and assets |
| Universal bootstrap | Same one-line install, reuse tunnel/key by Enter | Real PTY tests and runtime readback |
| MCP backend | A/B staging, compatibility check, drain and rollback | MCP tools, version and transaction journal |
| Tunnel-client | Pinned verified release, controlled restart | Service and tunnel health |
| Auto-update launcher | Self-update from verified committed release | SHA-256 installed file matches release |
| systemd timer/service | Self-update to 30-second polling | SHA-256, enabled+active, next firing |
| Private MCP extension | Preserve registered local overlay | No breaking semantic tool contracts |
| Update failure evidence | Local journal + receipt without exposing secrets | SHA-256 receipt and logs |
| CI/Release failures | GitHub issue, reconcile successful rerun | Run ID and issue state |
| Every deployed host | Confirm identity and tunnel before mutation | Repeated readback from distinct endpoints |

## Installation inventory categories

1. Original production VPS: hosts additional Sonoryx semantic MCP tools.
   Preserve the local Python update wrapper via the root-owned 0600
   file /etc/serverbridge/update-wrapper.path before migrating the custom
   auto-update launcher. Never deploy an upstream-only runtime without its
   compatibility and tool-registration checks.
2. New VPS: verify its unique identity and dedicated Tunnel ID, then install
   with the standard bootstrap. Do not use a shared tunnel for root commands.
3. Unresolved additional responder: do not mutate until ownership and
   operational scope are independently established.
4. Additional installed Linux hosts: inventory before assuming they exist.

## First adoption from legacy v0.5.10 through v0.5.14

An old updater cannot update its own script and timer until a new release is
successfully activated. An authenticated one-time migration must first
activate v0.5.15 or newer, then run the same overlay-aware updater once more.
After that, updater components are reconciled on future stable releases.
Do not replace a custom launcher without registering its local hook first.

## Live acceptance criteria

- Stable hostname/machine identity and dedicated tunnel on repeated calls.
- New Python runtime version, all desired exec/write/process/service flags.
- Existing MCP tools and semantic extensions preserved without schema drift.
- Verified current SHA-256 for auto-update launcher and systemd units.
- Active/enabled 30-second timer and next firing timestamp.
- Transport-client version, authenticated supervisor and backend health.
- Previous release, backups and rollback path intact.
- Every failed attempt recorded with cause, reproducibility, next action
  and sanitized issue/receipt; no unverified DONE label.

The 30-second timer polls for stable releases, not unreviewed code commits.
It cannot guarantee zero latency: GitHub/CDN propagation, network downtime,
and compatibility/rollback validation require real elapsed time. Auto-update
does not authorize bypassing GitHub protections, local security constraints
or human approval for production cutover.
