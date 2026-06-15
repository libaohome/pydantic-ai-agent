"""MCP Fetch Server — 独立的网页抓取 MCP 服务

使用方式：
1. pip install mcp
2. python mcp_servers/fetch_server.py
3. 在 Agent 配置中连接此 MCP 服务器
"""

from __future__ import annotations

import json
import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent

# 创建 MCP Server
mcp = Server("fetch")


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="fetch_url",
            description="Fetch the content of a URL and return it as text",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "max_length": {
                        "type": "integer",
                        "description": "Maximum response length",
                        "default": 5000,
                    },
                },
                "required": ["url"],
            },
        )
    ]


@mcp.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "fetch_url":
        url = arguments["url"]
        max_length = arguments.get("max_length", 5000)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            content = resp.text[:max_length]
            return [TextContent(type="text", text=content)]
    raise ValueError(f"Unknown tool: {name}")


if __name__ == "__main__":
    from starlette.applications import Starlette
    from starlette.routing import Route

    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp.run(streams[0], streams[1], mcp.create_initialization_options())

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=sse.handle_post_message, methods=["POST"]),
        ]
    )

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3001)
