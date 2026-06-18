"""单元测试 — Agent 运行器与统一返回结构。"""

from __future__ import annotations

import pytest

from app.agents import run_agent
from app.agents.registry import AgentName
from app.models.schemas import AgentRunRequest, AgentRunResult


@pytest.mark.asyncio
async def test_run_chat_model_with_test_model(monkeypatch):
    from app.core.llm_manager import get_llm_manager

    monkeypatch.setattr(get_llm_manager(), "resolve_model", lambda alias=None: "test")
    result = await run_agent(
        AgentName.chat_model,
        AgentRunRequest(user_input="hello"),
    )
    assert result.is_success
    assert isinstance(result.output, dict)
    assert "text" in result.output


@pytest.mark.asyncio
async def test_run_chat_model_rejects_image_generation_alias():
    result = await run_agent(
        AgentName.chat_model,
        AgentRunRequest(user_input="画猫", model_alias="sensenova-u1-fast"),
    )
    assert not result.is_success
    assert result.error is not None
    assert "image-gen" in result.error


@pytest.mark.asyncio
async def test_run_image_gen_agent(monkeypatch, tmp_path):
    import base64
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.core.llm_manager import ModelConfig
    from app.core.uploads import UploadStore

    store = UploadStore(root=tmp_path)
    monkeypatch.setattr("app.agents.image_gen.get_download_store", lambda: store)
    monkeypatch.setattr(
        "app.agents.image_gen.get_llm_manager",
        lambda: type(
            "L",
            (),
            {
                "has_alias": lambda _self, a: a == "sensenova-u1-fast",
                "get_config": lambda _self, _a: ModelConfig(
                    alias="sensenova-u1-fast",
                    model_name="sensenova-u1-fast",
                    provider="openai",
                    model_id="sensenova-u1-fast",
                    credential_group="sensenova",
                ),
                "get_credentials": lambda _self, _g: ("k", "https://api.example.com/v1"),
            },
        )(),
    )

    png_bytes = b"\x89PNG generated"
    mock_resp = MagicMock()
    mock_resp.is_error = False
    mock_resp.json.return_value = {
        "data": [{"b64_json": base64.standard_b64encode(png_bytes).decode("ascii")}],
    }
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.agents.image_gen.httpx.AsyncClient", return_value=mock_client):
        result = await run_agent(
            AgentName.image_gen,
            AgentRunRequest(user_input="画一只猫", model_alias="sensenova-u1-fast"),
        )

    assert result.is_success
    assert result.output["artifacts"]


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
