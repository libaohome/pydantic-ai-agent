"""图编排 — 使用 pydantic-graph 构建多 Agent 协作工作流"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import logfire
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from app.core.deps import AgentDeps
from app.agents.registry import AgentName, get_agent

RouteKind = Literal["qa", "review", "analyze"]


def classify_route(user_input: str) -> RouteKind:
    """根据用户输入分类路由目标（规则路由，可替换为 LLM 意图分类）。"""
    text = user_input.lower()

    # Skill / 天气 / 图像检测 / 通用问答 — 优先于宽泛的「查询」
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

    # 数据分析：需明确数据语境，避免「查询天气」误命中
    if any(kw in text for kw in ["数据", "统计", "报表", "分析", "订单", "sql", "数据库"]):
        return "analyze"
    if "查询" in text and any(kw in text for kw in ["数据", "统计", "订单", "表", "数据库"]):
        return "analyze"

    return "qa"


# ─── 图状态 ──────────────────────────────────────

@dataclass
class WorkflowState:
    """工作流共享状态"""

    user_input: str = ""
    tenant_id: str = "default"
    user_id: str = "anonymous"
    # 各阶段结果
    analysis_result: str = ""
    review_result: str = ""
    qa_result: str = ""
    # 路由决策
    needs_review: bool = False
    needs_qa: bool = False
    # 错误信息
    error: str = ""


# ─── 节点定义 ────────────────────────────────────

@dataclass
class RouterNode(BaseNode[WorkflowState]):
    """路由节点 — 分析用户意图，决定执行路径"""

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
    """数据分析节点"""

    async def run(self, ctx: GraphRunContext[WorkflowState]) -> End[WorkflowState]:
        with logfire.span("analyze_node"):
            agent = get_agent(AgentName.data_analyst)
            deps = AgentDeps(
                tenant_id=ctx.state.tenant_id,
                user_id=ctx.state.user_id,
            )

            try:
                result = await agent.run(ctx.state.user_input, deps=deps)
                ctx.state.analysis_result = result.output.model_dump_json()
            except Exception as e:
                ctx.state.error = str(e)

            return End(ctx.state)


@dataclass
class ReviewNode(BaseNode[WorkflowState]):
    """代码审查节点"""

    async def run(self, ctx: GraphRunContext[WorkflowState]) -> End[WorkflowState]:
        with logfire.span("review_node"):
            agent = get_agent(AgentName.code_reviewer)
            deps = AgentDeps(
                tenant_id=ctx.state.tenant_id,
                user_id=ctx.state.user_id,
            )

            try:
                result = await agent.run(ctx.state.user_input, deps=deps)
                ctx.state.review_result = result.output.model_dump_json()
            except Exception as e:
                ctx.state.error = str(e)

            return End(ctx.state)


@dataclass
class QaNode(BaseNode[WorkflowState]):
    """知识问答节点"""

    async def run(self, ctx: GraphRunContext[WorkflowState]) -> End[WorkflowState]:
        with logfire.span("qa_node"):
            agent = get_agent(AgentName.qa_assistant)
            deps = AgentDeps(
                tenant_id=ctx.state.tenant_id,
                user_id=ctx.state.user_id,
            )

            try:
                result = await agent.run(ctx.state.user_input, deps=deps)
                ctx.state.qa_result = result.output.model_dump_json()
            except Exception as e:
                ctx.state.error = str(e)

            return End(ctx.state)


# ─── 构建图 ──────────────────────────────────────

agent_workflow = Graph[WorkflowState](
    nodes=[RouterNode, AnalyzeNode, ReviewNode, QaNode],
    name="agent-workflow",
)
