from __future__ import annotations

import asyncio
import os

os.environ["SERVERBRIDGE_ENABLE_EXEC"] = "1"

from mcp import Client

from serverbridge.server import mcp

EXPECTED_TOOLS = {
    "server_info",
    "list_files",
    "read_text",
    "service_status",
    "service_logs",
    "process_list",
    "run_command",
}


async def main() -> None:
    async with Client(mcp, raise_exceptions=True) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}

        missing = EXPECTED_TOOLS - names
        assert not missing, f"Missing MCP tools: {sorted(missing)}"

        calls = [
            ("server_info", {}),
            ("list_files", {"path": ".", "limit": 10}),
            ("read_text", {"path": "README.md", "max_bytes": 4096}),
            ("process_list", {"limit": 5}),
            ("run_command", {"argv": ["python", "-c", "print('bridge-exec-ok')"], "cwd": ".", "timeout_seconds": 10}),
        ]

        for name, arguments in calls:
            result = await client.call_tool(name, arguments=arguments)
            assert not result.is_error, f"{name} failed: {result}"


if __name__ == "__main__":
    asyncio.run(main())
