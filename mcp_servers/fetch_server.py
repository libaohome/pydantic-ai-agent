"""
MCP Fetch Server — 独立的网页抓取 MCP 服务。

MCP（Model Context Protocol）允许外部工具以标准协议向 AI Agent 暴露能力。
本服务提供一个工具 ``fetch_url``：GET 指定 URL 并返回文本内容。

启动方式：
1. pip install mcp httpx starlette uvicorn
2. python mcp_servers/fetch_server.py
3. 在 Agent 或 Cursor 配置中通过 SSE 连接 http://localhost:3001/sse

协议端点：
- GET  /sse       — SSE 长连接，供 MCP 客户端握手
- POST /messages  — MCP 消息 POST 入口

面向小白：
- @mcp.list_tools 注册工具列表（名称、描述、JSON Schema）
- @mcp.call_tool 在客户端调用工具时执行实际逻辑
"""

from __future__ import annotations

import json
import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent

# 创建名为 "fetch" 的 MCP Server 实例
mcp = Server("fetch")


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """
    MCP 协议回调：向客户端声明本服务器提供的工具列表。

    客户端连接后会先调用此处理器获取可用工具及参数 schema。
    """
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
    """
    MCP 协议回调：执行具体工具调用。

    参数:
            name: 工具名，当前仅支持 fetch_url
            arguments: 客户端传入的参数字典

    返回:
            TextContent 列表（MCP 标准响应格式）
    """
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
    # 直接运行本文件时，用 Starlette 提供 SSE HTTP 服务
    from starlette.applications import Starlette
    from starlette.routing import Route

    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        """处理 /sse 端点的 SSE 连接，将读写流交给 mcp.run。"""
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
