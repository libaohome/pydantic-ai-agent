"""FastAPI 路由 — Agent / Workflow API 接口。"""

from fastapi import APIRouter

from app.agents import AgentName, list_agents, run_agent
from app.graphs import WorkflowName, list_workflows, run_workflow
from app.core.llm import get_llm_manager
from app.models.schemas import (
    AgentRunRequest,
    AgentRunResult,
    WorkflowRunRequest,
    WorkflowRunResult,
)

router = APIRouter(prefix="/agents", tags=["agents"])


# ─── 列表接口 ────────────────────────────────────

@router.get("/")
async def list_capabilities():
    """列出所有可用 Agent 与 Workflow。"""
    return {"agents": list_agents(), "workflows": list_workflows()}


# ─── 通用 Agent 运行 ─────────────────────────────

@router.post("/{name}/agent", response_model=AgentRunResult)
async def run_agent_by_name(name: AgentName, body: AgentRunRequest) -> AgentRunResult:
    """通用 Agent 运行端点，返回统一的 success/error 信封结构。"""
    return await run_agent(name, body)


# ─── 通用 Workflow 运行 ──────────────────────────

@router.post("/{workflow_name}/workflow", response_model=WorkflowRunResult)
async def run_workflow_by_name(
    workflow_name: WorkflowName,
    body: WorkflowRunRequest,
) -> WorkflowRunResult:
    """通用 Workflow 运行端点，返回统一的 success/error 信封结构。"""
    return await run_workflow(workflow_name, body)


# ─── 成本报告 ────────────────────────────────────

@router.get("/costs")
async def get_costs():
    """获取 LLM 调用的成本追踪报告。"""
    llm = get_llm_manager()
    return {"costs": llm.get_cost_report()}
