"""Agent 运行器 — 统一的 Agent 执行入口与结果封装。"""

from __future__ import annotations

import time
import uuid
from typing import Any, cast

import logfire
from pydantic_ai.usage import UsageLimits

from app.agents.input_files import prepare_agent_input
from app.agents.chat_media import (
    build_chat_user_prompt,
    get_chat_builtin_tools,
    resolve_chat_model_alias,
    run_sensenova_image_generation,
    serialize_chat_model_result,
    supports_image_generation,
)
from app.agents.registry import AgentName, get_agent
from app.core.deps import AgentDeps, db_session_scope
from app.core.llm import MODEL_REGISTRY, ModelAlias, get_llm_manager
from app.models.schemas import AgentRunRequest, AgentRunResult, TokenUsage


async def run_agent(agent_name: AgentName, request: AgentRunRequest) -> AgentRunResult:
    """运行指定 Agent 并返回统一的 success/error 结构。"""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    with logfire.span(
        "run_agent",
        agent=agent_name.value,
        request_id=request_id,
        tenant_id=request.tenant_id,
        user_id=request.user_id,
        session_id=request.session_id,
    ):
        agent = get_agent(agent_name)
        effective_alias: ModelAlias | None = None
        if request.model_alias:
            if request.model_alias not in MODEL_REGISTRY:
                elapsed = round(time.time() - start_time, 3)
                error = f"Unknown model alias: {request.model_alias}"
                return AgentRunResult(
                    request_id=request_id,
                    agent=agent_name.value,
                    tenant_id=request.tenant_id,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    status="error",
                    error=error,
                    elapsed_seconds=elapsed,
                )
            effective_alias = cast(ModelAlias, request.model_alias)
            llm = get_llm_manager()
            agent.model = llm.resolve_model(effective_alias)
        else:
            effective_alias = resolve_chat_model_alias(None) if agent_name == AgentName.chat_model else None

        if agent_name == AgentName.chat_model:
            user_prompt = build_chat_user_prompt(
                request.user_input,
                request.file_ids,
                model_alias=request.model_alias,
            )
        else:
            user_prompt = prepare_agent_input(agent_name, request.user_input, request.file_ids)

        deps = AgentDeps(
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            session_id=request.session_id,
            request_id=request_id,
            file_ids=request.file_ids,
        )

        run_kwargs: dict[str, Any] = {"deps": deps}
        if agent_name == AgentName.chat_model:
            run_kwargs["builtin_tools"] = get_chat_builtin_tools(request.model_alias)
        if agent_name == AgentName.data_analyst:
            run_kwargs["usage_limits"] = UsageLimits(request_limit=12, tool_calls_limit=8)

        try:
            if (
                agent_name == AgentName.chat_model
                and effective_alias
                and supports_image_generation(effective_alias)
            ):
                output_data = await run_sensenova_image_generation(request.user_input)
                elapsed = round(time.time() - start_time, 3)
                return AgentRunResult(
                    request_id=request_id,
                    agent=agent_name.value,
                    tenant_id=request.tenant_id,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    status="success",
                    output=output_data,
                    usage=TokenUsage(request_tokens=0, response_tokens=0),
                    cost_usd=0.0,
                    elapsed_seconds=elapsed,
                )

            async def _invoke(db_session: Any = None) -> Any:
                if db_session is not None:
                    deps.db_session = db_session
                return await agent.run(user_prompt, **run_kwargs)

            if agent_name == AgentName.data_analyst:
                async with db_session_scope() as session:
                    result = await _invoke(session)
            else:
                result = await _invoke()

            elapsed = round(time.time() - start_time, 3)
            if agent_name == AgentName.chat_model:
                output_data = serialize_chat_model_result(result)
            else:
                output_data = _serialize_output(result.output)
            usage = result.usage()
            token_usage = TokenUsage(
                request_tokens=usage.request_tokens if usage else 0,
                response_tokens=usage.response_tokens if usage else 0,
            )
            cost_alias = effective_alias or get_llm_manager()._default_alias()
            cost = get_llm_manager().track_cost(
                cost_alias,
                token_usage.request_tokens,
                token_usage.response_tokens,
            )

            return AgentRunResult(
                request_id=request_id,
                agent=agent_name.value,
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                session_id=request.session_id,
                status="success",
                output=output_data,
                usage=token_usage,
                cost_usd=round(cost, 6),
                elapsed_seconds=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start_time, 3)
            logfire.error("agent_run_failed", error=str(e), request_id=request_id)
            return AgentRunResult(
                request_id=request_id,
                agent=agent_name.value,
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                session_id=request.session_id,
                status="error",
                error=str(e),
                elapsed_seconds=elapsed,
            )


def _serialize_output(output: Any) -> Any:
    if hasattr(output, "model_dump"):
        return output.model_dump()
    return str(output)
