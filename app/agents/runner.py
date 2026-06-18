"""Agent 运行器 — 统一的 Agent 执行入口与结果封装。"""

from __future__ import annotations

import time
import uuid
from typing import Any, cast

import logfire
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from app.agents.chat_media import (
    build_chat_user_prompt,
    resolve_agent_for_model_alias,
    resolve_chat_model_alias,
    serialize_chat_model_result,
    supports_image_generation,
)
from app.agents.image_gen import resolve_image_gen_alias, run_image_generation
from app.agents.input_files import get_upload_store, prepare_agent_input
from app.agents.registry import AgentName, build_runtime_config, get_agent
from app.core.deps import AgentDeps, RuntimeConfigKeys as RC, db_session_scope
from app.core.llm_manager import ModelAlias, get_llm_manager
from app.models.schemas import AgentRunRequest, AgentRunResult, TokenUsage


def _error_result(
    *,
    request_id: str,
    agent: str,
    request: AgentRunRequest,
    error: str,
    elapsed: float,
) -> AgentRunResult:
    return AgentRunResult(
        request_id=request_id,
        agent=agent,
        tenant_id=request.tenant_id,
        user_id=request.user_id,
        session_id=request.session_id,
        status="error",
        error=error,
        elapsed_seconds=elapsed,
    )


def _success_result(
    *,
    request_id: str,
    agent: str,
    request: AgentRunRequest,
    output: Any,
    token_usage: TokenUsage,
    cost_usd: float,
    elapsed: float,
) -> AgentRunResult:
    return AgentRunResult(
        request_id=request_id,
        agent=agent,
        tenant_id=request.tenant_id,
        user_id=request.user_id,
        session_id=request.session_id,
        status="success",
        output=output,
        usage=token_usage,
        cost_usd=cost_usd,
        elapsed_seconds=elapsed,
    )


def _resolve_effective_alias(
    agent_name: AgentName,
    request: AgentRunRequest,
    runtime_config: dict[str, Any],
) -> ModelAlias | None:
    if request.model_alias:
        return cast(ModelAlias, request.model_alias)
    if runtime_config.get(RC.IMAGE_GEN):
        return resolve_image_gen_alias(None)
    if runtime_config.get(RC.RESOLVE_DEFAULT_MODEL):
        return resolve_chat_model_alias(None)
    return None


def _validate_model_for_agent(
    agent_name: AgentName,
    runtime_config: dict[str, Any],
    effective_alias: ModelAlias | None,
) -> str | None:
    if not effective_alias:
        return None
    is_image_model = supports_image_generation(effective_alias)
    if runtime_config.get(RC.IMAGE_GEN):
        if not is_image_model:
            return f"Model {effective_alias!r} is not an image generation model; use chat-model instead"
        return None
    if runtime_config.get(RC.PROMPT_BUILDER) == "chat_media" and is_image_model:
        return (
            f"Model {effective_alias!r} is an image generation model; "
            "use image-gen agent or select a chat/multimodal model"
        )
    return None


def _build_user_prompt(
    agent_name: AgentName,
    request: AgentRunRequest,
    runtime_config: dict[str, Any],
) -> str | list[Any]:
    if runtime_config.get(RC.PROMPT_BUILDER) == "chat_media":
        return build_chat_user_prompt(
            request.user_input,
            request.file_ids,
            model_alias=request.model_alias,
        )
    return prepare_agent_input(agent_name, request.user_input, request.file_ids)


def _build_run_kwargs(deps: AgentDeps) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"deps": deps}
    limits = deps.runtime_config.get(RC.USAGE_LIMITS)
    if limits:
        kwargs["usage_limits"] = UsageLimits(**limits) if isinstance(limits, dict) else limits
    return kwargs


def _serialize_result(result: Any, runtime_config: dict[str, Any]) -> Any:
    if runtime_config.get(RC.OUTPUT_SERIALIZER) == "chat_model":
        return serialize_chat_model_result(result)
    output = result.output
    if hasattr(output, "model_dump"):
        return output.model_dump()
    return str(output)


async def _invoke_agent(
    agent: Agent[AgentDeps, Any],
    user_prompt: str | list[Any],
    deps: AgentDeps,
    run_kwargs: dict[str, Any],
) -> Any:
    if deps.runtime_config.get(RC.NEEDS_DB_SESSION):
        async with db_session_scope() as session:
            deps.db_session = session
            return await agent.run(user_prompt, **run_kwargs)
    return await agent.run(user_prompt, **run_kwargs)


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
        runtime_config = build_runtime_config(agent_name, request.runtime_config)

        if request.model_alias and not get_llm_manager().has_alias(request.model_alias):
            elapsed = round(time.time() - start_time, 3)
            return _error_result(
                request_id=request_id,
                agent=agent_name.value,
                request=request,
                error=f"Unknown model alias: {request.model_alias}",
                elapsed=elapsed,
            )

        effective_alias = _resolve_effective_alias(agent_name, request, runtime_config)
        model_error = _validate_model_for_agent(agent_name, runtime_config, effective_alias)
        if model_error:
            elapsed = round(time.time() - start_time, 3)
            return _error_result(
                request_id=request_id,
                agent=agent_name.value,
                request=request,
                error=model_error,
                elapsed=elapsed,
            )

        if effective_alias and not runtime_config.get(RC.IMAGE_GEN):
            agent.model = get_llm_manager().resolve_model(effective_alias)

        store = get_upload_store()
        meta_files = [store.get_metadata(fid) for fid in request.file_ids]
        deps = AgentDeps(
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            session_id=request.session_id,
            request_id=request_id,
            meta_files=meta_files,
            runtime_config=runtime_config,
        )

        try:
            if runtime_config.get(RC.IMAGE_GEN):
                alias = effective_alias or resolve_image_gen_alias(None)
                output = await run_image_generation(request.user_input, alias)
                elapsed = round(time.time() - start_time, 3)
                return _success_result(
                    request_id=request_id,
                    agent=agent_name.value,
                    request=request,
                    output=output,
                    token_usage=TokenUsage(),
                    cost_usd=0.0,
                    elapsed=elapsed,
                )

            user_prompt = _build_user_prompt(agent_name, request, runtime_config)
            run_kwargs = _build_run_kwargs(deps)
            result = await _invoke_agent(agent, user_prompt, deps, run_kwargs)
            elapsed = round(time.time() - start_time, 3)
            output_data = _serialize_result(result, runtime_config)
            usage = result.usage
            token_usage = TokenUsage(
                request_tokens=usage.input_tokens if usage else 0,
                response_tokens=usage.output_tokens if usage else 0,
            )
            cost_alias = effective_alias or get_llm_manager().default_alias()
            cost = get_llm_manager().track_cost(
                cost_alias,
                token_usage.request_tokens,
                token_usage.response_tokens,
            )
            return _success_result(
                request_id=request_id,
                agent=agent_name.value,
                request=request,
                output=output_data,
                token_usage=token_usage,
                cost_usd=round(cost, 6),
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start_time, 3)
            logfire.error("agent_run_failed", error=str(e), request_id=request_id)
            return _error_result(
                request_id=request_id,
                agent=agent_name.value,
                request=request,
                error=str(e),
                elapsed=elapsed,
            )


def resolve_agent_name_for_model(model_alias: str | None) -> AgentName:
    """按 model_alias 能力路由到 chat-model 或 image-gen。"""
    return resolve_agent_for_model_alias(model_alias)
