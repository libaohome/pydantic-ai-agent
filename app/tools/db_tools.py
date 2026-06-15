"""数据库查询工具 — 数据分析 Agent 专用"""

from __future__ import annotations

from pydantic_ai import RunContext

from app.core.deps import AgentDeps


async def execute_sql(
    ctx: RunContext[AgentDeps],
    query: str,
    limit: int = 100,
) -> str:
    """执行只读 SQL 查询（SELECT only）

    安全检查：
    1. 只允许 SELECT 语句
    2. 强制 LIMIT 限制
    3. 返回 JSON 格式结果
    """
    import json
    from sqlalchemy import text

    # 安全：只允许 SELECT
    normalized = query.strip().upper()
    if not normalized.startswith("SELECT"):
        return "Error: Only SELECT queries are allowed"

    # 强制 LIMIT
    if "LIMIT" not in normalized:
        query = query.rstrip(";") + f" LIMIT {limit}"

    if ctx.deps.db_session is None:
        return "Error: No database session available"

    try:
        result = await ctx.deps.db_session.execute(text(query))
        rows = result.mappings().all()
        return json.dumps(
            [dict(row) for row in rows],
            default=str,
            ensure_ascii=False,
        )
    except Exception as e:
        return f"SQL Error: {e}"


async def list_tables(ctx: RunContext[AgentDeps]) -> str:
    """列出数据库中的所有表"""
    from sqlalchemy import text

    if ctx.deps.db_session is None:
        return "Error: No database session available"

    result = await ctx.deps.db_session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    )
    tables = [row[0] for row in result]
    return "\n".join(tables)


async def describe_table(ctx: RunContext[AgentDeps], table_name: str) -> str:
    """描述表结构"""
    import json
    from sqlalchemy import text

    if ctx.deps.db_session is None:
        return "Error: No database session available"

    result = await ctx.deps.db_session.execute(
        text(f"PRAGMA table_info({table_name})")
    )
    columns = [
        {
            "name": row[1],
            "type": row[2],
            "notnull": bool(row[3]),
            "default": row[4],
            "pk": bool(row[5]),
        }
        for row in result
    ]
    return json.dumps(columns, ensure_ascii=False, indent=2)
