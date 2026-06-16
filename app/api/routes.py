"""FastAPI 路由 — Agent API 接口。

本模块定义了所有与 Agent 相关的 HTTP 端点，是前端或外部系统调用 AI 能力的入口。

提供的接口包括：
- ``GET /agents/``：列出所有可用 Agent
- ``POST /agents/code-review``：代码审查
- ``POST /agents/data-analysis``：数据分析
- ``POST /agents/qa``：知识问答
- ``POST /agents/run``：图编排工作流（自动路由）
- ``GET /agents/costs``：LLM 成本报告

面向小白的关键概念：
- **APIRouter**：FastAPI 的路由分组器，可设置统一前缀和标签。
- **Depends**：依赖注入，FastAPI 会自动解析并传入依赖对象（本文件部分端点未使用）。
- **response_model**：声明响应体的 Pydantic 模型，用于校验和生成 OpenAPI 文档。
- **HTTPException**：主动抛出 HTTP 错误（如 400、500），FastAPI 会转成 JSON 错误响应。
"""

from __future__ import annotations

import uuid  # 生成全局唯一标识符，用于追踪单次请求
import time  # 计时，统计 Agent 运行耗时
from typing import Any, cast  # Any：任意类型；cast：告诉类型检查器做显式类型转换

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

# 创建路由组：所有路径自动加上 /agents 前缀，Swagger 文档中归入 "agents" 标签
router = APIRouter(prefix="/agents", tags=["agents"])


# ─── 通用运行函数 ────────────────────────────────

async def _run_agent(
    agent_name: AgentName,
    user_input: str,
    tenant_id: str = "default",
    user_id: str = "anonymous",
    model_alias: str | None = None,
) -> dict[str, Any]:
    """运行指定 Agent 并返回结果与元数据。

    这是三个业务端点（code-review、data-analysis、qa）的共用执行逻辑，
    负责：获取 Agent、预处理输入、可选切换模型、注入依赖、调用 run、统计用量。

    Args:
        agent_name: 要运行的 Agent 枚举名称。
        user_input: 传给 Agent 的用户输入文本。
        tenant_id: 租户 ID，用于多租户隔离，默认 "default"。
        user_id: 用户 ID，默认 "anonymous"。
        model_alias: 可选的模型别名，传入时会动态替换 Agent 使用的模型。

    Returns:
        包含 request_id、output、usage、cost_usd、elapsed_seconds、status 等字段的字典。
        出错时 status 为 "error"，并包含 error 字段。
    """
    # uuid4() 生成随机 UUID；[:8] 只取前 8 位作为简短请求 ID
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()  # 记录开始时间戳（秒）

    # logfire.span：创建一个可观测性追踪片段，便于在监控平台查看调用链
    with logfire.span(
        "run_agent",
        agent=agent_name.value,
        request_id=request_id,
        tenant_id=tenant_id,
    ):
        agent = get_agent(agent_name)  # 从注册表获取 Agent 实例

        # 代码审查 Agent 需要特殊预处理：无代码时追加提示，避免盲目调工具
        if agent_name == AgentName.code_reviewer:
            from app.agents.code_reviewer import prepare_review_input

            user_input = prepare_review_input(user_input)

        # 动态切换模型：请求参数中指定了 model_alias 时覆盖 Agent 默认模型
        if model_alias:
            from app.core.llm import MODEL_REGISTRY, ModelAlias, get_llm_manager

            if model_alias not in MODEL_REGISTRY:
                # HTTPException(状态码, 详情)：FastAPI 会将其转为 JSON 错误响应
                raise HTTPException(400, f"Unknown model alias: {model_alias}")
            llm = get_llm_manager()
            # cast：静态类型提示，运行时无效果，仅帮助 IDE/类型检查器
            alias = cast(ModelAlias, model_alias)
            model_str = llm.resolve_model_string(alias)
            agent.model = model_str  # 直接修改 Agent 实例的 model 属性

        # 构造依赖注入对象，Agent.run() 时通过 deps= 传入
        deps = AgentDeps(
            tenant_id=tenant_id,
            user_id=user_id,
            request_id=request_id,
        )

        try:
            # await：异步等待 Agent 完成推理和工具调用
            result = await agent.run(user_input, deps=deps)
            elapsed = round(time.time() - start_time, 3)  # 保留 3 位小数的耗时（秒）

            # 结构化输出用 model_dump() 转 dict；纯字符串则直接 str()
            output_data = result.output.model_dump() if hasattr(result.output, "model_dump") else str(result.output)

            # 成本追踪：根据 token 用量估算费用（简化公式，单价为示例值）
            cost = 0.0
            if result.usage():
                usage = result.usage()
                # 简化版成本追踪：输入 token 和输出 token 分别按百万单价计费
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
            # 捕获所有异常，返回错误结构而非让 FastAPI 直接 500（由上层端点决定是否抛 HTTPException）
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
    """列出所有可用 Agent 及其元信息。

    Returns:
        ``{"agents": [...]}`` 格式的 JSON，agents 列表由 ``list_agents()`` 生成。
    """
    return {"agents": list_agents()}


# ─── 代码审查 ────────────────────────────────────

@router.post("/code-review", response_model=CodeReviewOutput)
async def code_review(
    body: CodeReviewInput,
    tenant_id: str = "default",
    user_id: str = "anonymous",
    model: str | None = None,
):
    """代码审查 Agent 端点。

    接收代码片段和语言类型，调用 code-reviewer Agent 返回结构化审查报告。

    Args:
        body: 请求体，包含 code、language、context 等字段（Pydantic 自动校验）。
        tenant_id: 查询参数，租户 ID。
        user_id: 查询参数，用户 ID。
        model: 查询参数，可选模型别名。

    Returns:
        CodeReviewOutput：包含 issues、score、passed、summary 等字段。

    Raises:
        HTTPException(500): Agent 运行失败时抛出。
    """
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
    """数据分析 Agent 端点。

    接收自然语言分析需求和数据源说明，返回分析结论与图表规格。

    Args:
        body: 请求体，包含 query、data_source 等字段。
        tenant_id: 租户 ID。
        user_id: 用户 ID。
        model: 可选模型别名。

    Returns:
        DataAnalysisOutput：分析结论、图表、SQL 记录等。

    Raises:
        HTTPException(500): Agent 运行失败时抛出。
    """
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
    """知识问答 Agent 端点。

    接收用户问题，搜索知识库/互联网后返回带来源和置信度的回答。

    Args:
        body: 请求体，包含 question 字段。
        tenant_id: 租户 ID。
        user_id: 用户 ID。
        model: 可选模型别名。

    Returns:
        QaOutput：answer、sources、confidence、follow_up_questions 等。

    Raises:
        HTTPException(500): Agent 运行失败时抛出。
    """
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
    """运行图编排工作流，自动路由到合适的 Agent。

    与上面三个专用端点不同，此接口使用 pydantic-graph 工作流：
    先由 RouterNode 根据关键词判断意图，再执行对应的 AnalyzeNode / ReviewNode / QaNode。

    Args:
        user_input: 用户自然语言输入（查询参数）。
        tenant_id: 租户 ID。
        user_id: 用户 ID。

    Returns:
        包含 elapsed_seconds 和 state（各阶段结果摘要，最多 500 字符）的 JSON。
    """
    from app.graphs.workflow import agent_workflow, WorkflowState, RouterNode

    start_time = time.time()
    # 初始化工作流共享状态对象
    state = WorkflowState(
        user_input=user_input,
        tenant_id=tenant_id,
        user_id=user_id,
    )

    # 从 RouterNode 开始执行图；run 返回包含最终 state 的结果对象
    result = await agent_workflow.run(start_node=RouterNode(), state=state)
    workflow_state = result.state

    elapsed = round(time.time() - start_time, 3)
    return {
        "elapsed_seconds": elapsed,
        "state": {
            # 结果截断到 500 字符，避免响应体过大
            "analysis_result": workflow_state.analysis_result[:500] if workflow_state.analysis_result else None,
            "review_result": workflow_state.review_result[:500] if workflow_state.review_result else None,
            "qa_result": workflow_state.qa_result[:500] if workflow_state.qa_result else None,
            "error": workflow_state.error or None,
        },
    }


# ─── 成本报告 ────────────────────────────────────

@router.get("/costs")
async def get_costs():
    """获取 LLM 调用的成本追踪报告。

    Returns:
        ``{"costs": ...}``，内容由 LLM 管理器的 ``get_cost_report()`` 提供。
    """
    llm = get_llm_manager()
    return {"costs": llm.get_cost_report()}
