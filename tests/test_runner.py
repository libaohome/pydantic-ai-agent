"""单元测试 — Agent 运行器与统一返回结构。"""

import pytest

from app.agents import run_agent
from app.agents.registry import AgentName
from app.models.schemas import AgentRunRequest, AgentRunResult


@pytest.mark.asyncio
async def test_run_chat_model_with_test_model():
    from app.agents.chat_model import chat_model_agent

    chat_model_agent.model = "test"
    result = await run_agent(
        AgentName.chat_model,
        AgentRunRequest(user_input="hello"),
    )
    assert result.is_success
    assert isinstance(result.output, dict)
    assert "text" in result.output


@pytest.mark.asyncio
async def test_run_agent_unknown_model_returns_error_result():
    result = await run_agent(
        AgentName.qa_assistant,
        AgentRunRequest(user_input="hi", model_alias="not-a-real-model"),
    )
    assert not result.is_success
    assert result.error is not None
    assert "Unknown model alias" in result.error


def test_agent_run_result_success_and_error_share_fields():
    success = AgentRunResult(
        request_id="abc",
        agent="qa-assistant",
        tenant_id="tenant01",
        user_id="user01",
        session_id="session01",
        status="success",
        output={"answer": "ok"},
        elapsed_seconds=1.0,
    )
    error = AgentRunResult(
        request_id="abc",
        agent="qa-assistant",
        tenant_id="tenant01",
        user_id="user01",
        session_id="session01",
        status="error",
        error="boom",
        elapsed_seconds=0.5,
    )

    assert success.is_success
    assert not error.is_success
    assert set(AgentRunResult.model_fields) == set(error.model_fields)
