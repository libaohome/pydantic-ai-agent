"""图编排 — 使用 pydantic-graph 构建多 Agent 协作工作流。

本模块实现了一个简单的「意图路由 + 单 Agent 执行」工作流：
1. **RouterNode**：根据用户输入关键词判断应走哪条路径
2. **AnalyzeNode / ReviewNode / QaNode**：分别调用数据分析、代码审查、知识问答 Agent
3. **End**：图执行的终止节点，携带最终 ``WorkflowState``

面向小白的关键概念：
- **Graph（图）**：由多个 Node（节点）和边（run 方法的返回值）组成的状态机。
- **BaseNode**：节点基类，子类实现 ``async def run()``，返回值决定下一个节点。
- **GraphRunContext**：节点运行时上下文，通过 ``ctx.state`` 读写共享状态。
- **@dataclass**：自动生成 ``__init__`` 等样板代码，适合存放纯数据的状态类。
- **Literal**：类型注解，表示变量只能是几个固定字符串之一（如 "qa" | "review" | "analyze"）。
"""

from __future__ import annotations

from dataclasses import dataclass, field  # dataclass 装饰器：简化数据类的定义
from typing import Literal  # Literal：字面量类型，限制值为固定几个选项

import logfire
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from app.core.deps import AgentDeps
from app.agents.registry import AgentName, get_agent

# RouteKind 只能是 "qa"、"review"、"analyze" 三个字符串之一
RouteKind = Literal["qa", "review", "analyze"]


def classify_route(user_input: str) -> RouteKind:
    """根据用户输入分类路由目标。

    使用关键词规则做意图识别（非 LLM），可后续替换为模型分类。
    匹配顺序很重要：问答类关键词优先，避免「查询天气」被误判为数据分析。

    Args:
        user_input: 用户原始输入文本。

    Returns:
        "qa"、"review" 或 "analyze" 之一。
    """
    text = user_input.lower()  # 转小写，实现大小写不敏感匹配

    # Skill / 天气 / 图像检测 / 通用问答 — 优先于宽泛的「查询」
    if any(kw in text for kw in [
        "skill", "skills", "天气", "weather", "气温", "预报", "forecast",
        "伪造", "篡改", "假图", "修图", "取证", "forgery", "tamper",
        "image-forgery", "检测图片", "图片检测",
        "什么是", "为什么", "如何", "怎么", "解释", "怎么样", "你可以", "你能",
    ]):
        return "qa"
    # 复合条件：同时包含「检测」和图片相关词时走问答（如图片伪造检测 skill）
    if "检测" in text and any(kw in text for kw in ["图", "image", "照片", "png", "jpg", "jpeg"]):
        return "qa"

    if any(kw in text for kw in ["审查", "review", "代码质量", "bug", "代码审查"]):
        return "review"

    # 数据分析：需明确数据语境，避免「查询天气」误命中
    if any(kw in text for kw in ["数据", "统计", "报表", "分析", "订单", "sql", "数据库"]):
        return "analyze"
    if "查询" in text and any(kw in text for kw in ["数据", "统计", "订单", "表", "数据库"]):
        return "analyze"

    return "qa"  # 默认兜底：未匹配到明确意图时走知识问答


# ─── 图状态 ──────────────────────────────────────

@dataclass
class WorkflowState:
    """工作流在各节点之间传递的共享状态。

    所有节点通过 ``ctx.state`` 读写此对象，实现数据在图中的流转。
    pydantic-graph 不要求状态类继承特定基类，用 dataclass 即可。
    """

    user_input: str = ""       # 用户原始输入
    tenant_id: str = "default" # 租户 ID
    user_id: str = "anonymous" # 用户 ID
    file_ids: list[str] = field(default_factory=list)  # 上传文件 ID 列表
    # 各阶段结果（JSON 字符串形式，由对应 Agent 的 model_dump_json() 填充）
    analysis_result: str = ""
    review_result: str = ""
    qa_result: str = ""
    # 路由决策标记（RouterNode 设置，可供后续扩展多步流程使用）
    needs_review: bool = False
    needs_qa: bool = False
    # 错误信息：任一节点异常时写入，不中断图执行
    error: str = ""


# ─── 节点定义 ────────────────────────────────────
# 每个节点是 BaseNode 的子类，run 方法的返回值类型声明了「下一跳」可能的目标节点。
# 返回 End(state) 表示图执行结束；返回其他 Node 实例则继续执行该节点。

@dataclass
class RouterNode(BaseNode[WorkflowState]):
    """路由节点 — 分析用户意图，决定执行路径。

    工作流的入口节点：读取 user_input，调用 classify_route，返回对应业务节点。
    """

    async def run(self, ctx: GraphRunContext[WorkflowState]) -> AnalyzeNode | ReviewNode | QaNode | End[WorkflowState]:
        """执行路由逻辑。

        Args:
            ctx: 图运行上下文，``ctx.state`` 为 WorkflowState 实例。

        Returns:
            下一个要执行的节点实例（AnalyzeNode / ReviewNode / QaNode）。
        """
        with logfire.span("router_node", input=ctx.state.user_input[:100]):
            route = classify_route(ctx.state.user_input)

            if route == "analyze":
                ctx.state.needs_review = False
                ctx.state.needs_qa = False
                return AnalyzeNode()  # 返回节点实例 = 图的「边」指向该节点

            if route == "review":
                ctx.state.needs_review = True
                return ReviewNode()

            ctx.state.needs_qa = True
            return QaNode()


@dataclass
class AnalyzeNode(BaseNode[WorkflowState]):
    """数据分析节点 — 调用 data_analyst Agent 并写入 analysis_result。"""

    async def run(self, ctx: GraphRunContext[WorkflowState]) -> End[WorkflowState]:
        """运行数据分析 Agent。

        Args:
            ctx: 图运行上下文。

        Returns:
            End(ctx.state)：携带更新后状态的终止节点。
        """
        with logfire.span("analyze_node"):
            from app.agents.data_analyst import prepare_analysis_input

            agent = get_agent(AgentName.data_analyst)
            deps = AgentDeps(
                tenant_id=ctx.state.tenant_id,
                user_id=ctx.state.user_id,
                file_ids=ctx.state.file_ids,
            )

            try:
                prompt = prepare_analysis_input(ctx.state.user_input, ctx.state.file_ids)
                result = await agent.run(prompt, deps=deps)
                # model_dump_json()：Pydantic 模型转 JSON 字符串，便于存入 state
                ctx.state.analysis_result = result.output.model_dump_json()
            except Exception as e:
                ctx.state.error = str(e)

            return End(ctx.state)  # End 表示图执行到此结束


@dataclass
class ReviewNode(BaseNode[WorkflowState]):
    """代码审查节点 — 调用 code_reviewer Agent 并写入 review_result。"""

    async def run(self, ctx: GraphRunContext[WorkflowState]) -> End[WorkflowState]:
        """运行代码审查 Agent。

        Args:
            ctx: 图运行上下文。

        Returns:
            End(ctx.state)：携带更新后状态的终止节点。
        """
        with logfire.span("review_node"):
            from app.agents.code_reviewer import prepare_review_input

            agent = get_agent(AgentName.code_reviewer)
            deps = AgentDeps(
                tenant_id=ctx.state.tenant_id,
                user_id=ctx.state.user_id,
                file_ids=ctx.state.file_ids,
            )

            try:
                prompt = prepare_review_input(ctx.state.user_input, ctx.state.file_ids)
                result = await agent.run(prompt, deps=deps)
                ctx.state.review_result = result.output.model_dump_json()
            except Exception as e:
                ctx.state.error = str(e)

            return End(ctx.state)


@dataclass
class QaNode(BaseNode[WorkflowState]):
    """知识问答节点 — 调用 qa_assistant Agent 并写入 qa_result。"""

    async def run(self, ctx: GraphRunContext[WorkflowState]) -> End[WorkflowState]:
        """运行知识问答 Agent。

        Args:
            ctx: 图运行上下文。

        Returns:
            End(ctx.state)：携带更新后状态的终止节点。
        """
        with logfire.span("qa_node"):
            from app.agents.qa_assistant import prepare_qa_input

            agent = get_agent(AgentName.qa_assistant)
            deps = AgentDeps(
                tenant_id=ctx.state.tenant_id,
                user_id=ctx.state.user_id,
                file_ids=ctx.state.file_ids,
            )

            try:
                prompt = prepare_qa_input(ctx.state.user_input, ctx.state.file_ids)
                result = await agent.run(prompt, deps=deps)
                ctx.state.qa_result = result.output.model_dump_json()
            except Exception as e:
                ctx.state.error = str(e)

            return End(ctx.state)


# ─── 构建图 ──────────────────────────────────────
# Graph 把节点类注册到图中；run 时传入 start_node 实例和初始 state 即可执行。

agent_workflow = Graph[WorkflowState](
    nodes=[RouterNode, AnalyzeNode, ReviewNode, QaNode],  # 传入节点类（非实例）
    name="agent-workflow",  # 图名称，用于日志和调试
)
