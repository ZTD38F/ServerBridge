# Automatic release adoption canary — v0.5.16

This release intentionally does not change runtime endpoints, token processing,
container operation or MCP tools. It verifies the previous v0.5.15 updater
installation can autonomously discover and deploy the next stable version.

Acceptance must be proven separately on each authorized host using its actual
installed version, a real scheduled trigger, verified A/B commit journal,
retained local semantic tools, and active update timer. The GitHub Release
itself is not proof of production deployment. No secrets or host IDs are
published in this public file.
