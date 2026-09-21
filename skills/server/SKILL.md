# ServerBridge operating guidance

Use ServerBridge as the primary backend for server administration.

- Read before overwriting an existing file.
- Prefer structured tools over `run_command` when a structured tool exists.
- Use argv arrays; do not wrap ordinary commands in a shell unless shell syntax is genuinely required.
- Verify consequential writes by reading the resulting state.
- Never report a service/file change as successful solely because a command was submitted.
- Do not expose environment variables or credentials in logs or responses.
- For destructive or broad operations, narrow the target first and verify it.
