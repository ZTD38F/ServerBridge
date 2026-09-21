# ServerBridge operating guidance

Use ServerBridge as the primary backend for server inspection.

- Prefer structured tools for filesystem, service, process and system inspection.
- Verify observations before reporting them as facts.
- Do not expose environment variables or credentials in logs or responses.
- Treat access to server files and logs as sensitive infrastructure access.
- If an operation is not available as an exposed tool, state that limitation instead of claiming it was performed.
