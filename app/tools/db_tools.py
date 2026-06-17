"""
数据库查询工具模块 — 专为「数据分析 Agent」设计。

本模块提供只读 SQL 查询能力，Agent 可用它探索数据库结构并执行 SELECT。
当前实现面向 SQLite（list_tables / describe_table 使用 sqlite 系统表）。

安全设计（面向小白）：
- 只允许 SELECT，禁止 INSERT/UPDATE/DELETE 等写操作
- 若用户 SQL 未写 LIMIT，会自动追加 LIMIT，防止一次返回过多行
- 所有操作都需要 ctx.deps.db_session（SQLAlchemy 异步会话）

典型调用链：Agent 工具 → execute_sql / list_tables / describe_table → 数据库
"""

from __future__ import annotations

from pydantic_ai import RunContext

from app.core.deps import AgentDeps


async def execute_sql(
    ctx: RunContext[AgentDeps],
    query: str,
    limit: int = 100,
) -> str:
    """
    执行只读 SQL 查询并返回 JSON 格式结果。

    参数:
            ctx: 运行上下文，必须包含有效的 db_session
            query: SQL 查询语句（仅允许 SELECT 开头）
            limit: 当 SQL 中无 LIMIT 时自动追加的行数上限，默认 100

    返回:
            JSON 数组字符串，每个元素为一行数据的字典；
            出错时返回 "Error: ..." 或 "SQL Error: ..." 文本
    """
    import json
    from sqlalchemy import text

    # 安全：只允许 SELECT（去掉首尾空白后转大写判断）
    normalized = query.strip().upper()
    if not normalized.startswith("SELECT"):
        return "Error: Only SELECT queries are allowed"

    # 强制 LIMIT：避免 Agent 写出无限制的 SELECT * 拖垮内存
    if "LIMIT" not in normalized:
        query = query.rstrip(";") + f" LIMIT {limit}"

    if ctx.deps.db_session is None:
        return "Error: No database session available"

    try:
        result = await ctx.deps.db_session.execute(text(query))
        rows = result.mappings().all()  # 每行是类字典的 RowMapping
        payload = [dict(row) for row in rows]
        if not payload:
            return json.dumps(
                {"message": "查询成功，0 行记录", "rows": []},
                ensure_ascii=False,
            )
        return json.dumps(payload, default=str, ensure_ascii=False)
    except Exception as e:
        return f"SQL Error: {e}"


async def list_tables(ctx: RunContext[AgentDeps]) -> str:
    """
    列出数据库中所有用户表名（SQLite 专用）。

    参数:
            ctx: 运行上下文，需含 db_session

    返回:
            每行一个表名的文本；无会话时返回错误信息
    """
    from sqlalchemy import text

    if ctx.deps.db_session is None:
        return "Error: No database session available"

    # sqlite_master 是 SQLite 内置系统表，type='table' 表示用户表
    result = await ctx.deps.db_session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    )
    tables = [row[0] for row in result]
    if not tables:
        return "（数据库中暂无用户表）"
    return "\n".join(tables)


async def describe_table(ctx: RunContext[AgentDeps], table_name: str) -> str:
    """
    描述指定表的结构（列名、类型、是否非空、默认值、是否主键）。

    参数:
            ctx: 运行上下文
            table_name: 表名（注意：当前未做标识符转义，仅适合受控环境）

    返回:
            JSON 格式的列信息列表
    """
    import json
    from sqlalchemy import text

    if ctx.deps.db_session is None:
        return "Error: No database session available"

    # PRAGMA table_info 是 SQLite 查看表结构的命令
    result = await ctx.deps.db_session.execute(
        text(f"PRAGMA table_info({table_name})")
    )
    columns = [
        {
            "name": row[1],       # 列名
            "type": row[2],       # 数据类型
            "notnull": bool(row[3]),
            "default": row[4],
            "pk": bool(row[5]),  # 是否主键
        }
        for row in result
    ]
    return json.dumps(columns, ensure_ascii=False, indent=2)
