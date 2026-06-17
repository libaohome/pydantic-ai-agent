"""Agent 路由工作流 — 意图识别后调用对应 Agent。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

import logfire
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from app.agents.registry import AgentName
from app.agents.runner import run_agent
from app.models.schemas import AgentRunRequest

RouteKind = Literal["qa", "review", "analyze"]


def classify_route(user_input: str) -> RouteKind:
    """根据用户输入分类路由目标。"""
    text = user_input.lower()

    if any(kw in text for kw in [
        "skill", "skills", "天气", "weather", "气温", "预报", "forecast",
        "伪造", "篡改", "假图", "修图", "取证", "forgery", "tamper",
        "image-forgery", "检测图片", "图片检测",
        "什么是", "为什么", "如何", "怎么", "解释", "怎么样", "你可以", "你能",
    ]):
        return "qa"
    if "检测" in text and any(kw in text for kw in ["图", "image", "照片", "png", "jpg", "jpeg"]):
        return "qa"

    if any(kw in text for kw in ["审查", "review", "代码质量", "bug", "代码审查"]):
        return "review"

    if any(kw in text for kw in ["数据", "统计", "报表", "分析", "订单", "sql", "数据库"]):
        return "analyze"
    if "查询" in text and any(kw in text for kw in ["数据", "统计", "订单", "表", "数据库"]):
        return "analyze"

    return "qa"


@dataclass
class WorkflowState:
    """工作流在各节点之间传递的共享状态。"""

    user_input: str = ""
    tenant_id: str = "tenant01"
    user_id: str = "user01"
    session_id: str = "session01"
    file_ids: list[str] = field(default_factory=list)
    analysis_result: str = ""
    review_result: str = ""
    qa_result: str = ""
    needs_review: bool = False
    needs_qa: bool = False
    error: str = ""


def _agent_request(state: WorkflowState) -> AgentRunRequest:
    return AgentRunRequest(
        user_input=state.user_input,
        tenant_id=state.tenant_id,
        user_id=state.user_id,
        session_id=state.session_id,
        file_ids=state.file_ids,
    )


async def _run_node_agent(state: WorkflowState, agent_name: AgentName, field_name: str) -> None:
    result = await run_agent(agent_name, _agent_request(state))
    if result.is_success:
        setattr(state, field_name, json.dumps(result.output, ensure_ascii=False))
    else:
        state.error = result.error or "Agent run failed"


@dataclass
class RouterNode(BaseNode[WorkflowState]):
    async def run(self, ctx: GraphRunContext[WorkflowState]) -> AnalyzeNode | ReviewNode | QaNode | End[WorkflowState]:
        with logfire.span("router_node", input=ctx.state.user_input[:100]):
            route = classify_route(ctx.state.user_input)

            if route == "analyze":
                ctx.state.needs_review = False
                ctx.state.needs_qa = False
                return AnalyzeNode()

            if route == "review":
                ctx.state.needs_review = True
                return ReviewNode()

            ctx.state.needs_qa = True
            return QaNode()


@dataclass
class AnalyzeNode(BaseNode[WorkflowState]):
    async def run(self, ctx: GraphRunContext[WorkflowState]) -> End[WorkflowState]:
        with logfire.span("analyze_node"):
            try:
                await _run_node_agent(ctx.state, AgentName.data_analyst, "analysis_result")
            except Exception as e:
                ctx.state.error = str(e)
            return End(ctx.state)


@dataclass
class ReviewNode(BaseNode[WorkflowState]):
    async def run(self, ctx: GraphRunContext[WorkflowState]) -> End[WorkflowState]:
        with logfire.span("review_node"):
            try:
                await _run_node_agent(ctx.state, AgentName.code_reviewer, "review_result")
            except Exception as e:
                ctx.state.error = str(e)
            return End(ctx.state)


@dataclass
class QaNode(BaseNode[WorkflowState]):
    async def run(self, ctx: GraphRunContext[WorkflowState]) -> End[WorkflowState]:
        with logfire.span("qa_node"):
            try:
                await _run_node_agent(ctx.state, AgentName.qa_assistant, "qa_result")
            except Exception as e:
                ctx.state.error = str(e)
            return End(ctx.state)


agent_router_workflow = Graph[WorkflowState](
    nodes=[RouterNode, AnalyzeNode, ReviewNode, QaNode],
    name="agent-router",
)

# 兼容旧名称
agent_workflow = agent_router_workflow
