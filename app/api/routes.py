"""FastAPI 路由 — Agent API 接口"""

from __future__ import annotations

import uuid
import time
from typing import Any

import logfire
from fastapi import APIRouter, HTTPException, Depends

from app.core.deps import AgentDeps, get_session
from app.core.llm import get_llm_manager
from app.agents.registry import get_agent, list_agents, AgentName
from app.models.schemas import (
    CodeReviewInput, CodeReviewOutput,
    DataAnalysisInput, DataAnalysisOutput,
    QaInput, QaOutput,
    ErrorResponse,
)

router = APIRouter(prefix="/agents", tags=["agents"])


# ─── 通用运行函数 ────────────────────────────────

async def _run_agent(
    agent_name: AgentName,
    user_input: str,
    tenant_id: str = "default",
    user_id: str = "anonymous",
    model_alias: str | None = None,
) -> dict[str, Any]:
    """运行指定 Agent 并返回结果 + 元数据"""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    with logfire.span(
        "run_agent",
        agent=agent_name.value,
        request_id=request_id,
        tenant_id=tenant_id,
    ):
        agent = get_agent(agent_name)

        # 动态切换模型
        if model_alias:
            llm = get_llm_manager()
            from app.core.llm import ModelAlias as MA
            try:
                alias = MA(model_alias)
                model_str = llm.resolve_model_string(alias)
                agent.model = model_str
            except ValueError:
                raise HTTPException(400, f"Unknown model alias: {model_alias}")

        deps = AgentDeps(
            tenant_id=tenant_id,
            user_id=user_id,
            request_id=request_id,
        )

        try:
            result = await agent.run(user_input, deps=deps)
            elapsed = round(time.time() - start_time, 3)

            output_data = result.output.model_dump() if hasattr(result.output, "model_dump") else str(result.output)

            # 成本追踪
            cost = 0.0
            if result.usage():
                usage = result.usage()
                # 简化版成本追踪
                cost = (usage.request_tokens or 0) / 1_000_000 * 0.27 + \
                       (usage.response_tokens or 0) / 1_000_000 * 1.10

            return {
                "request_id": request_id,
                "agent": agent_name.value,
                "output": output_data,
                "usage": {
                    "request_tokens": result.usage().request_tokens if result.usage() else 0,
                    "response_tokens": result.usage().response_tokens if result.usage() else 0,
                },
                "cost_usd": round(cost, 6),
                "elapsed_seconds": elapsed,
                "status": "success",
            }

        except Exception as e:
            elapsed = round(time.time() - start_time, 3)
            logfire.error("agent_run_failed", error=str(e), request_id=request_id)
            return {
                "request_id": request_id,
                "agent": agent_name.value,
                "output": None,
                "error": str(e),
                "elapsed_seconds": elapsed,
                "status": "error",
            }


# ─── 列表接口 ────────────────────────────────────

@router.get("/")
async def get_agents():
    """列出所有可用 Agent"""
    return {"agents": list_agents()}


# ─── 代码审查 ────────────────────────────────────

@router.post("/code-review", response_model=CodeReviewOutput)
async def code_review(
    body: CodeReviewInput,
    tenant_id: str = "default",
    user_id: str = "anonymous",
    model: str | None = None,
):
    """代码审查 Agent"""
    result = await _run_agent(
        AgentName.code_reviewer,
        user_input=f"Review the following {body.language} code:\n\n{body.code}\n\nContext: {body.context}",
        tenant_id=tenant_id,
        user_id=user_id,
        model_alias=model,
    )
    if result["status"] == "error":
        raise HTTPException(500, result["error"])
    return result["output"]


# ─── 数据分析 ────────────────────────────────────

@router.post("/data-analysis", response_model=DataAnalysisOutput)
async def data_analysis(
    body: DataAnalysisInput,
    tenant_id: str = "default",
    user_id: str = "anonymous",
    model: str | None = None,
):
    """数据分析 Agent"""
    result = await _run_agent(
        AgentName.data_analyst,
        user_input=f"分析需求: {body.query}\n数据源: {body.data_source}",
        tenant_id=tenant_id,
        user_id=user_id,
        model_alias=model,
    )
    if result["status"] == "error":
        raise HTTPException(500, result["error"])
    return result["output"]


# ─── 知识问答 ────────────────────────────────────

@router.post("/qa", response_model=QaOutput)
async def qa(
    body: QaInput,
    tenant_id: str = "default",
    user_id: str = "anonymous",
    model: str | None = None,
):
    """知识问答 Agent"""
    result = await _run_agent(
        AgentName.qa_assistant,
        user_input=body.question,
        tenant_id=tenant_id,
        user_id=user_id,
        model_alias=model,
    )
    if result["status"] == "error":
        raise HTTPException(500, result["error"])
    return result["output"]


# ─── 通用执行（运行图工作流）─────────────────────

@router.post("/run")
async def run_workflow(
    user_input: str,
    tenant_id: str = "default",
    user_id: str = "anonymous",
):
    """运行图编排工作流（自动路由到合适的 Agent）"""
    from app.graphs.workflow import agent_workflow, WorkflowState, RouterNode

    start_time = time.time()
    state = WorkflowState(
        user_input=user_input,
        tenant_id=tenant_id,
        user_id=user_id,
    )

    result = await agent_workflow.run(start_node=RouterNode(), state=state)
    workflow_state = result.state

    elapsed = round(time.time() - start_time, 3)
    return {
        "elapsed_seconds": elapsed,
        "state": {
            "analysis_result": workflow_state.analysis_result[:500] if workflow_state.analysis_result else None,
            "review_result": workflow_state.review_result[:500] if workflow_state.review_result else None,
            "qa_result": workflow_state.qa_result[:500] if workflow_state.qa_result else None,
            "error": workflow_state.error or None,
        },
    }


# ─── 成本报告 ────────────────────────────────────

@router.get("/costs")
async def get_costs():
    """获取成本追踪报告"""
    llm = get_llm_manager()
    return {"costs": llm.get_cost_report()}
