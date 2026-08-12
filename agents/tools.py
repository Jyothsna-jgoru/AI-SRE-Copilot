from __future__ import annotations

import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from backend.config import get_settings


class MCPInvestigationClient:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or get_settings().mcp_server_url

    async def call(self, tool_name: str, arguments: dict) -> dict:
        async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments)
        if getattr(result, "structuredContent", None):
            return result.structuredContent
        for block in result.content:
            if getattr(block, "type", None) == "text":
                try:
                    return json.loads(block.text)
                except json.JSONDecodeError:
                    return {"tool": tool_name, "text": block.text, "evidence": []}
        return {"tool": tool_name, "evidence": []}

