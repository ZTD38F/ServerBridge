# Contributing

Stability is the first priority.

Before a pull request:

```bash
bash -n bootstrap.sh install.sh update.sh uninstall.sh scripts/check-upstream-tunnel.sh
shellcheck -x bootstrap.sh install.sh update.sh uninstall.sh scripts/check-upstream-tunnel.sh
python -m compileall -q serverbridge tests
python tests/mcp_smoke.py
python tests/security_smoke.py
python tests/test_installer_templates.py
```

For installer changes, the GitHub CI also performs a real temporary install and a forced failed update to verify rollback.

## Runtime lock

When `pyproject.toml` runtime dependencies change, regenerate the lock using the oldest supported Python version (currently Python 3.10):

```bash
python3.10 -m pip install 'pip-tools>=7.5,<8'
python3.10 -m piptools compile \
  --generate-hashes \
  --strip-extras \
  --resolver=backtracking \
  --output-file=requirements.lock \
  pyproject.toml
```

The lock must install successfully on every supported Python version in CI.

## Rules

- do not log credentials;
- never add a CLI argument for the runtime API key;
- never overwrite unrelated directories;
- preserve rollback behavior and previous service state;
- prefer an explicit unsupported-environment error over a risky guess;
- keep MCP stdio output clean;
- pin externally executed release artifacts and verify upstream checksums;
- keep the user-facing installer short even when internal checks grow.
