"""数据分析 Agent — 自然语言驱动的数据分析与可视化。

本模块定义了一个数据分析师角色的 AI Agent，能够：
1. 理解用户的自然语言分析需求
2. 通过数据库工具探索表结构和执行 SQL 查询
3. 生成分析结论、图表规格、SQL 记录和行动建议
4. 返回 ``DataAnalysisOutput`` 结构化结果

面向小白的关键概念：
- **只读 SQL**：安全规则限制只能执行 SELECT，防止误删改数据。
- **工具链**：list_tables → describe_table → execute_sql 是典型的数据探索流程。
- **结构化输出**：图表类型、字段映射等由 Pydantic 模型约束，便于前端渲染。
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent, RunContext

from app.core.deps import AgentDeps, RuntimeConfigKeys as RC
from app.models.schemas import DataAnalysisOutput

RUNTIME_CONFIG: dict[str, Any] = {
    RC.NEEDS_DB_SESSION: True,
    RC.USAGE_LIMITS: {"request_limit": 12, "tool_calls_limit": 8},
}


# ─── Agent 定义 ──────────────────────────────────

data_analysis_agent = Agent[AgentDeps, DataAnalysisOutput](
    model="deepseek:deepseek-chat",
    output_type=DataAnalysisOutput,
    deps_type=AgentDeps,
    retries=2,
    instructions="""你是一名数据分析师。你的任务：

1. 理解用户的数据分析需求，尽快输出 DataAnalysisOutput（不要无限调用工具）
2. 数据库工具（名称必须准确）：
   - `list_db_tables`：列出所有表（**最多调用 1 次**）
   - `describe_db_table`：查看表结构（每张表 **最多 1 次**）
   - `query_data`：执行 SELECT（**同类统计 SQL 不要重复执行**）

3. 推荐流程（一轮完成即可）：
   list_db_tables → describe_db_table(conversations) → 用 1～3 条 SELECT 完成统计 → 输出结论

4. 分析查询结果，生成：
   - analysis：清晰结论（表为空时明确写「当前无数据」）
   - charts：可为空列表；无数据时用 table 展示 0 行说明
   - sql_query：记录主要 SQL
   - recommendations：行动建议

5. 图表数据格式：
   - bar/line: x_field, y_field, data 为 [{x, y}]
   - pie: data 为 [{name, value}]
   - table: data 为 [{col1, col2, ...}]

**重要（避免死循环）：**
- 工具返回 Error: 或 SQL Error: 时，**不要**反复 list/describe/query；在 analysis 说明错误并结束
- 查询结果为空 `[]` 是有效结果，直接写「无记录」并输出 DataAnalysisOutput
- **总工具调用不超过 6 次**后必须输出最终结果
- 禁止重复调用 list_db_tables / describe_db_table

安全规则：仅 SELECT；不修改数据。
""",
)


# ─── 注册工具 ──────────────────────────────────
# 以下三个工具封装了数据库访问能力，Agent 会根据 instructions 按需调用。

@data_analysis_agent.tool
async def list_db_tables(ctx: RunContext[AgentDeps]) -> str:
    """列出数据库中所有表的名称。

    Args:
        ctx: 运行上下文，内含数据库连接等依赖。

    Returns:
        表名列表的字符串表示。
    """
    from app.tools.db_tools import list_tables
    return await list_tables(ctx)


@data_analysis_agent.tool
async def describe_db_table(ctx: RunContext[AgentDeps], table_name: str) -> str:
    """查看指定表的结构（字段名、类型、约束等）。

    Args:
        ctx: 运行上下文。
        table_name: 要查看的表名。

    Returns:
        表结构的描述字符串。
    """
    from app.tools.db_tools import describe_table
    return await describe_table(ctx, table_name)


@data_analysis_agent.tool
async def query_data(ctx: RunContext[AgentDeps], sql: str, limit: int = 100) -> str:
    """执行只读 SQL 查询。

    Args:
        ctx: 运行上下文。
        sql: SELECT 语句（非 SELECT 会被拒绝）。
        limit: 最大返回行数，默认 100，防止结果过大。

    Returns:
        查询结果的字符串表示。
    """
    from app.tools.db_tools import execute_sql
    return await execute_sql(ctx, sql, limit)
