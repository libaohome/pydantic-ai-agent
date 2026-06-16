"""
知识库与网络搜索工具模块 — 专为「知识问答 Agent」设计。

本模块提供两类检索能力：
1. search_knowledge_base — 在项目知识库中做向量相似度检索（当前为模拟数据）
2. search_web — 联网搜索（当前为模拟数据）

生产环境替换指南：
- 知识库：接入 Milvus / Qdrant / Pinecone / pgvector 等向量库
- 网络搜索：接入 SearXNG / Tavily / Serper 等搜索 API

面向小白：这两个函数都返回 JSON 字符串，Agent 会把它当作工具调用的结果继续推理。
"""

from __future__ import annotations

from pydantic_ai import RunContext

from app.core.deps import AgentDeps


async def search_knowledge_base(
    ctx: RunContext[AgentDeps],
    query: str,
    top_k: int = 5,
    threshold: float = 0.7,
) -> str:
    """
    在知识库中按语义相似度搜索与 query 相关的文档片段。

    参数:
            ctx: 运行上下文（预留，可注入向量库客户端）
            query: 用户问题或搜索关键词
            top_k: 最多返回几条结果
            threshold: 相似度分数下限，低于此分数的结果会被过滤

    返回:
            JSON 数组，每项含 content（正文）、source（来源路径）、score（分数）

    注意:
            当前为 mock 实现，便于本地开发与演示。
    """
    import json

    # TODO: 替换为实际向量检索（embedding + 向量库查询）
    mock_results = [
        {
            "content": f"关于 '{query}' 的知识条目 #1（模拟数据）",
            "source": "docs/architecture.md",
            "score": 0.95,
        },
        {
            "content": f"关于 '{query}' 的知识条目 #2（模拟数据）",
            "source": "docs/api-reference.md",
            "score": 0.88,
        },
    ]

    # 按阈值过滤后截取前 top_k 条
    filtered = [r for r in mock_results if r["score"] >= threshold][:top_k]
    return json.dumps(filtered, ensure_ascii=False, indent=2)


async def search_web(ctx: RunContext[AgentDeps], query: str, max_results: int = 5) -> str:
    """
    在互联网上搜索与 query 相关的网页摘要。

    参数:
            ctx: 运行上下文（预留）
            query: 搜索关键词
            max_results: 最多返回几条搜索结果

    返回:
            JSON 数组，每项含 title、url、snippet

    注意:
            当前为 mock 实现。
    """
    import json

    # TODO: 替换为实际搜索 API
    mock_results = [
        {
            "title": f"Search result for: {query}",
            "url": "https://example.com/result1",
            "snippet": "This is a mock search result...",
        }
    ]
    return json.dumps(mock_results[:max_results], ensure_ascii=False, indent=2)
