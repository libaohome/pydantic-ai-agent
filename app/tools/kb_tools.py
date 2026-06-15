"""知识库搜索工具 — 知识问答 Agent 专用"""

from __future__ import annotations

from pydantic_ai import RunContext

from app.core.deps import AgentDeps


async def search_knowledge_base(
    ctx: RunContext[AgentDeps],
    query: str,
    top_k: int = 5,
    threshold: float = 0.7,
) -> str:
    """搜索项目知识库（向量相似度检索）

    在生产环境中，替换为实际的向量数据库调用：
    - Milvus / Qdrant / Pinecone / Weaviate
    - 或 PostgreSQL + pgvector
    """
    import json

    # TODO: 替换为实际向量检索
    # 当前为模拟返回
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

    filtered = [r for r in mock_results if r["score"] >= threshold][:top_k]
    return json.dumps(filtered, ensure_ascii=False, indent=2)


async def search_web(ctx: RunContext[AgentDeps], query: str, max_results: int = 5) -> str:
    """网络搜索（接入 SearXNG / Tavily / Serper 等）

    生产环境替换为实际搜索 API
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
