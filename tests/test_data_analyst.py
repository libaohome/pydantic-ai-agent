"""单元测试 — 数据分析 Agent 防死循环与数据库会话。"""

import pytest
from pydantic_ai.usage import UsageLimits

from app.agents import run_agent
from app.agents.registry import AgentName
from app.models.schemas import AgentRunRequest


@pytest.mark.asyncio
async def test_data_analyst_empty_conversations_completes():
    """空表场景应在有限工具调用内返回结果，而非无限循环。"""
    from app.agents.data_analyst import data_analysis_agent

    data_analysis_agent.model = "test"
    result = await run_agent(
        AgentName.data_analyst,
        AgentRunRequest(
            user_input=(
                "分析 conversations 表：统计总记录数、按 agent_name 和 status 分组。"
                "若为空表请直接说明无数据。"
            ),
        ),
    )
    assert result.is_success, result.error
    assert isinstance(result.output, dict)
    assert "analysis" in result.output


@pytest.mark.asyncio
async def test_data_analyst_direct_run_with_session():
    """直接运行时应能 list 表且工具调用次数受限。"""
    from app.agents.data_analyst import data_analysis_agent
    from app.core.deps import AgentDeps, db_session_scope

    data_analysis_agent.model = "test"
    async with db_session_scope() as session:
        result = await data_analysis_agent.run(
            "用 list_db_tables 查看有哪些表，然后统计 conversations 行数，无数据也要给出结论。",
            deps=AgentDeps(db_session=session, tenant_id="tenant01"),
            usage_limits=UsageLimits(request_limit=10, tool_calls_limit=6),
        )
    assert result.output is not None
