"""Workflow 注册表 — 统一管理所有工作流图实例。"""

from enum import Enum

from pydantic_graph import Graph

from app.graphs.agent_router import WorkflowState, agent_router_workflow


class WorkflowName(str, Enum):
    """工作流名称枚举（对外 API 路径使用 ``.value``）。"""

    agent_router = "agent-router"


WORKFLOWS: dict[WorkflowName, Graph[WorkflowState]] = {
    WorkflowName.agent_router: agent_router_workflow,
}


def get_workflow(name: WorkflowName) -> Graph[WorkflowState]:
    return WORKFLOWS[name]


def list_workflows() -> list[dict[str, str]]:
    return [
        {
            "name": WorkflowName.agent_router.value,
            "description": "意图路由工作流：根据输入自动选择 QA / 代码审查 / 数据分析 Agent",
        },
    ]
