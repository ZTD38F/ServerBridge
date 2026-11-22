# ServerBridge verified release train

This describes candidate-creation automation, not a guarantee that every server
is deployed. Green CI is not a fleet receipt.

## Code commit to release proposal

1. GitHub CI runs on a push to the default main branch.
2. The release-proposal workflow runs only after CI succeeds. It checks that
   the successfully tested SHA still equals main HEAD, obtains the latest
   stable GitHub Release, and compares package, runtime and plugin versions.
3. If main still has the published version, release_train.py generates
   the next patch version in an isolated GitHub Actions checkout. If the
   source version is newer, it skips rather than duplicating a release.
   Invalid version metadata fails closed.
4. An existing open candidate PR takes priority. The bot never overwrites
   another release branch or force-pushes. It creates a draft version-only
   PR and explicitly dispatches the full CI matrix, because GITHUB_TOKEN
   write events do not reliably trigger ordinary workflows.
5. Promote the draft only after proving target fleet identity, rollback,
   source provenance and the complete candidate CI matrix.

## Green CI to stable release

The release workflow no longer publishes directly on a pyproject.toml push.
It requires successful CI of the exact live main SHA. Manual dispatch also
requires successful push CI for that SHA.

The known duplicate PH24 tunnel registration tracked in GitHub issue #29
is an explicit stable-publication safety gate. An open issue keeps
release creation skipped. Closing it requires independent host identity
and rollback evidence; merely closing the issue is not technical proof.

Approved stable releases keep SBOM, SHA256SUMS, provenance attestations,
versioned tar.gz / zip artifacts, and a published bootstrap/update script.

## Stable release to installed VPS

A v0.5.15+ native launcher checks stable GitHub releases using an enabled
approximately 30-second systemd timer. It verifies the archive checksum,
stages a candidate, checks MCP and tool schemas, switches the local route,
drains in-flight operations and retains the previous rollback generation.

This cannot be instantaneous because GitHub CI, artifact download,
health checks, network propagation and draining take time.

The legacy v10654 updater requires a separately authorized first adoption.
The new vps and legacy v10654 previously shared the same Tunnel ID.
Never execute privileged writes through the alternating PH24 MCP connector.
Use a uniquely pinned, authorized per-host provider console instead.

## Acceptance and failure rules

- Exact independently verified source SHA and manifest version.
- No untested production publish, duplicate PR or unsafe force-push.
- No privilege expansion, SSH bypass, DNS cutover, secret extraction or
  duplicate systemd timers.
- The original VPS keeps the Sonoryx semantic overlay; all 40 tool names
  and input schemas must match after updating.
- For each installed host, independently re-read hostname and machine ID,
  current release, updater/timer, tunnel PID, live MCP and streaming.
- Persist canonical Work Ledger receipts before saying VERIFIED or DONE.

Current limitation: The automated path prepares patch release candidates,
but automated production promotion remains gated until the PH24 identity
collision is resolved and the whole delivery chain passes E2E. Do not
claim fully unattended production releases while this gate remains open.
