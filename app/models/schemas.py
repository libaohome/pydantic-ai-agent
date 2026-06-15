"""Pydantic 模型 — Agent 的结构化输入/输出"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ─── 通用 ──────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str
    detail: str = ""


# ─── 代码审查 Agent ────────────────────────────

class CodeReviewInput(BaseModel):
    code: str = Field(description="待审查的源代码")
    language: str = Field(default="python", description="编程语言")
    context: str = Field(default="", description="额外上下文（如 PR 描述）")


class CodeIssue(BaseModel):
    line: int = Field(description="问题所在行号")
    severity: str = Field(description="严重程度: critical | warning | info")
    message: str = Field(description="问题描述")
    suggestion: str = Field(description="修复建议")


class CodeReviewOutput(BaseModel):
    summary: str = Field(description="审查总结")
    issues: list[CodeIssue] = Field(description="发现的问题列表")
    quality_score: int = Field(description="代码质量评分 0-100", ge=0, le=100)
    approved: bool = Field(description="是否通过审查")


# ─── 数据分析 Agent ────────────────────────────

class DataAnalysisInput(BaseModel):
    query: str = Field(description="用户的分析需求描述")
    data_source: str = Field(description="数据源标识")


class ChartSpec(BaseModel):
    chart_type: str = Field(description="图表类型: bar | line | pie | scatter | table")
    title: str = Field(description="图表标题")
    x_field: str = Field(default="", description="X 轴字段")
    y_field: str = Field(default="", description="Y 轴字段")
    data: list[dict] = Field(description="图表数据")


class DataAnalysisOutput(BaseModel):
    analysis: str = Field(description="分析结论")
    charts: list[ChartSpec] = Field(default_factory=list, description="可视化图表")
    sql_query: str = Field(default="", description="执行的 SQL 查询")
    recommendations: list[str] = Field(default_factory=list, description="行动建议")


# ─── 知识问答 Agent ────────────────────────────

class QaInput(BaseModel):
    question: str = Field(description="用户问题")
    domain: str = Field(default="general", description="知识领域")


class SourceReference(BaseModel):
    title: str
    url: str = ""
    snippet: str = ""


class QaOutput(BaseModel):
    answer: str = Field(description="回答内容")
    confidence: float = Field(description="置信度 0-1", ge=0, le=1)
    sources: list[SourceReference] = Field(default_factory=list, description="参考来源")
    follow_ups: list[str] = Field(default_factory=list, description="追问建议")
