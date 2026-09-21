from __future__ import annotations

import asyncio

from mcp import Client

from serverbridge.server import mcp

EXPECTED_TOOLS = {
    "server_info",
    "list_files",
    "read_text",
    "service_status",
    "service_logs",
    "process_list",
}


async def main() -> None:
    async with Client(mcp, raise_exceptions=True) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}

        missing = EXPECTED_TOOLS - names
        assert not missing, f"Missing MCP tools: {sorted(missing)}"

        result = await client.call_tool("server_info", arguments={})
        assert not result.is_error, result


if __name__ == "__main__":
    asyncio.run(main())
