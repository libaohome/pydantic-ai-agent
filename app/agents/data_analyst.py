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

from pydantic_ai import Agent, RunContext

from app.core.deps import AgentDeps
from app.core.llm import get_llm_manager
from app.models.schemas import DataAnalysisOutput


# ─── Agent 定义 ──────────────────────────────────

data_analysis_agent = Agent[AgentDeps, DataAnalysisOutput](
    model=get_llm_manager().resolve_model_string("deepseek-chat"),
    output_type=DataAnalysisOutput,  # 强制模型输出符合 DataAnalysisOutput  schema
    deps_type=AgentDeps,
    instructions="""你是一名数据分析师。你的任务：

1. 理解用户的数据分析需求
2. 使用数据库工具探索数据：
   - 先用 list_tables 了解数据结构
   - 再用 describe_table 查看表字段
   - 最后用 execute_sql 执行查询

3. 分析查询结果，生成：
   - 清晰的分析结论
   - 可视化图表规格（chart_type, title, data）
   - SQL 查询记录
   - 行动建议

4. 图表数据格式要求：
   - bar/line: 需要 x_field, y_field, data 为 [{x, y}] 数组
   - pie: data 为 [{name, value}] 数组
   - table: data 为 [{col1, col2, ...}] 数组

安全规则：
- 只能执行 SELECT 查询
- 所有查询自动添加 LIMIT 防止返回过多数据
- 不修改任何数据
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
