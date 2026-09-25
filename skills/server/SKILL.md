# ServerBridge operating guidance

Use ServerBridge as the primary backend for server inspection.

- Prefer structured tools over `run_command`: read/search/edit files with filesystem tools, control services with service tools, and use persistent process sessions for interactive or long-running work.
- Before editing an existing file, read it and use `expected_sha256` when practical; after mutation, verify the resulting state.
- Use `run_command` only when no structured tool covers the operation.
- Verify observations before reporting them as facts.
- Never expose environment variables or credentials in logs or responses; mutation output is centrally redacted and audited.
- Treat server files, process output and logs as sensitive infrastructure access.
- After restarting or changing a service, check its status and, for web services, use `tcp_probe` or `http_probe`.
- If an operation is not available as an exposed tool, state that limitation instead of claiming it was performed.
