# Contributing

Stability is the first priority.

Before a pull request:

```bash
bash -n install.sh update.sh uninstall.sh
python -m compileall -q serverbridge
```

Rules:

- do not log secrets;
- never add a CLI argument for the runtime API key;
- never overwrite unrelated directories;
- preserve rollback behavior;
- prefer an explicit unsupported-environment error over a risky guess;
- keep MCP stdio output clean;
- verify external downloads whenever upstream publishes checksums.
