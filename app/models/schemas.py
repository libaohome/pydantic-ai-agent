"""Pydantic 数据模型 — Agent 的结构化输入/输出与 API 契约。

本模块位于 ``app/models/`` 包内，定义**请求/响应的数据形状**（与数据库 ORM 无关）。

与 ``schema.py`` 的区别：
    - ``schemas.py``（本文件）：Pydantic ``BaseModel``，用于 API 校验、Agent 结构化输出
    - ``schema.py``：SQLAlchemy ORM，用于持久化到 SQLite

职责概览：
    - 为代码审查、数据分析、知识问答等 Agent 定义 Input/Output 模型
    - 提供通用 ``ErrorResponse`` 错误响应格式

在项目中的位置::

    app/
    └── models/
        ├── schemas.py   ← 当前文件（Pydantic 模型）
        ├── schema.py    ← SQLAlchemy ORM 表
        └── __init__.py
"""

from __future__ import annotations

from typing import Any, Literal

# ``BaseModel``：Pydantic 基类，自动做类型校验与 JSON 序列化
# ``Field``：为字段添加描述、默认值、校验规则（如 ge/le 范围）
from pydantic import BaseModel, Field


# ─── 通用 ──────────────────────────────────────

class ErrorResponse(BaseModel):
    """API 错误响应的标准格式。

    Attributes:
        error: 错误类型或简短错误码。
        detail: 详细错误说明，默认为空字符串。
    """

    error: str
    detail: str = ""


class AgentRunRequest(BaseModel):
    """通用 Agent 运行请求（``POST /agents/{name}/agent`` 请求体）。"""

    user_input: str = Field(description="传给 Agent 的用户输入文本")
    tenant_id: str = Field(default="tenant01", description="租户 ID")
    user_id: str = Field(default="user01", description="用户 ID")
    session_id: str = Field(default="session01", description="会话 ID")
    model_alias: str | None = Field(default=None, description="可选模型别名")
    file_ids: list[str] = Field(default_factory=list, description="上传文件 ID 列表")
    runtime_config: dict[str, Any] = Field(
        default_factory=dict,
        description="运行时配置，如 sandbox_root 沙箱根目录",
    )


class TokenUsage(BaseModel):
    """Token 用量统计。"""

    request_tokens: int = 0
    response_tokens: int = 0


class AgentRunResult(BaseModel):
    """Agent 运行结果信封（success / error 字段结构一致）。"""

    request_id: str
    agent: str
    tenant_id: str
    user_id: str
    session_id: str
    status: Literal["success", "error"]
    output: Any | None = None
    error: str | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    cost_usd: float = 0.0
    elapsed_seconds: float

    @property
    def is_success(self) -> bool:
        return self.status == "success"


class ChatMediaArtifact(BaseModel):
    """ChatModelAgent 返回的生成媒体文件。"""

    kind: Literal["image", "video", "audio", "file"] = "file"
    path: str = Field(description="磁盘绝对路径")
    mime_type: str = ""
    file_id: str = ""


class ChatModelOutput(BaseModel):
    """ChatModelAgent 结构化输出。"""

    text: str = Field(description="模型文本回复")
    artifacts: list[ChatMediaArtifact] = Field(default_factory=list)


class WorkflowRunRequest(BaseModel):
    """通用 Workflow 运行请求（``POST /agents/{workflow_name}/workflow`` 请求体）。"""

    user_input: str = Field(description="用户自然语言输入")
    tenant_id: str = Field(default="tenant01", description="租户 ID")
    user_id: str = Field(default="user01", description="用户 ID")
    session_id: str = Field(default="session01", description="会话 ID")
    file_ids: list[str] = Field(default_factory=list, description="上传文件 ID 列表")
    runtime_config: dict[str, Any] = Field(
        default_factory=dict,
        description="运行时配置，如 sandbox_root 沙箱根目录",
    )


class WorkflowStateSnapshot(BaseModel):
    """工作流执行后的状态摘要（各分支结果可能被截断）。"""

    analysis_result: str | None = None
    review_result: str | None = None
    qa_result: str | None = None
    error: str | None = None


class WorkflowRunResult(BaseModel):
    """Workflow 运行结果信封（success / error 字段结构一致）。"""

    request_id: str
    workflow: str
    tenant_id: str
    user_id: str
    session_id: str
    status: Literal["success", "error"]
    state: WorkflowStateSnapshot
    error: str | None = None
    elapsed_seconds: float

    @property
    def is_success(self) -> bool:
        return self.status == "success"


# ─── 代码审查 Agent ────────────────────────────

class CodeReviewInput(BaseModel):
    """代码审查 Agent 的输入参数。

    Attributes:
        code: 待审查的源代码文本。
        language: 编程语言标识，默认 python。
        context: 额外上下文，如 PR 描述、需求说明。
        file_ids: 可选的上传文件 ID 列表（data/upload 目录下文件名）。
    """

    code: str = Field(description="待审查的源代码")
    language: str = Field(default="python", description="编程语言")
    context: str = Field(default="", description="额外上下文（如 PR 描述）")
    file_ids: list[str] = Field(default_factory=list, description="上传文件 ID 列表")


class CodeIssue(BaseModel):
    """单条代码问题记录。

    Attributes:
        line: 问题所在行号（从 1 开始）。
        severity: 严重程度，取值为 critical | warning | info。
        message: 问题描述。
        suggestion: 修复建议。
    """

    line: int = Field(description="问题所在行号")
    severity: str = Field(description="严重程度: critical | warning | info")
    message: str = Field(description="问题描述")
    suggestion: str = Field(description="修复建议")


class CodeReviewOutput(BaseModel):
    """代码审查 Agent 的结构化输出。

    Pydantic AI 可将 LLM 回复解析为此模型，保证字段类型与约束。

    Attributes:
        summary: 审查总结。
        issues: 发现的问题列表。
        quality_score: 代码质量评分，0–100（``ge=0, le=100`` 约束范围）。
        approved: 是否通过审查。
    """

    summary: str = Field(description="审查总结")
    issues: list[CodeIssue] = Field(description="发现的问题列表")
    quality_score: int = Field(description="代码质量评分 0-100", ge=0, le=100)
    approved: bool = Field(description="是否通过审查")


# ─── 数据分析 Agent ────────────────────────────

class DataAnalysisInput(BaseModel):
    """数据分析 Agent 的输入参数。

    Attributes:
        query: 用户的自然语言分析需求。
        data_source: 数据源标识（表名、数据集 ID 等）。
        file_ids: 可选的上传文件 ID 列表。
    """

    query: str = Field(description="用户的分析需求描述")
    data_source: str = Field(description="数据源标识")
    file_ids: list[str] = Field(default_factory=list, description="上传文件 ID 列表")


class ChartSpec(BaseModel):
    """图表规格描述，供前端渲染可视化。

    Attributes:
        chart_type: 图表类型：bar | line | pie | scatter | table。
        title: 图表标题。
        x_field: X 轴对应的数据字段名。
        y_field: Y 轴对应的数据字段名。
        data: 图表数据行列表，每行是一个 dict。
    """

    chart_type: str = Field(description="图表类型: bar | line | pie | scatter | table")
    title: str = Field(description="图表标题")
    x_field: str = Field(default="", description="X 轴字段")
    y_field: str = Field(default="", description="Y 轴字段")
    data: list[dict] = Field(description="图表数据")


class DataAnalysisOutput(BaseModel):
    """数据分析 Agent 的结构化输出。

    Attributes:
        analysis: 文字分析结论。
        charts: 可视化图表列表，默认空列表。
        sql_query: 实际执行的 SQL（若有）。
        recommendations: 行动建议列表。
    """

    analysis: str = Field(description="分析结论")
    # ``default_factory=list``：每次创建实例时调用 list() 生成新列表，避免共享可变默认值
    charts: list[ChartSpec] = Field(default_factory=list, description="可视化图表")
    sql_query: str = Field(default="", description="执行的 SQL 查询")
    recommendations: list[str] = Field(default_factory=list, description="行动建议")


# ─── 知识问答 Agent ────────────────────────────

class QaInput(BaseModel):
    """知识问答 Agent 的输入参数。

    Attributes:
        question: 用户提出的问题。
        domain: 知识领域，如 general、finance、medical。
        file_ids: 可选的上传文件 ID 列表。
    """

    question: str = Field(description="用户问题")
    domain: str = Field(default="general", description="知识领域")
    file_ids: list[str] = Field(default_factory=list, description="上传文件 ID 列表")


class SourceReference(BaseModel):
    """引用来源条目。

    Attributes:
        title: 来源标题。
        url: 来源链接，可选。
        snippet: 相关片段摘要，可选。
    """

    title: str
    url: str = ""
    snippet: str = ""


class QaOutput(BaseModel):
    """知识问答 Agent 的结构化输出。

    Attributes:
        answer: 回答正文。
        confidence: 置信度 0–1，由模型或后处理给出。
        sources: 参考来源列表。
        follow_ups: 建议的追问问题列表。
    """

    answer: str = Field(description="回答内容")
    confidence: float = Field(description="置信度 0-1", ge=0, le=1)
    sources: list[SourceReference] = Field(default_factory=list, description="参考来源")
    follow_ups: list[str] = Field(default_factory=list, description="追问建议")
