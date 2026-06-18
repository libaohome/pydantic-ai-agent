"""单元测试 — 代码审查 Agent 及相关工具。

测试目的：
1. **CodeReviewAgent**：验证 Agent 输出类型、Pydantic Schema 字段、数据模型校验
2. **prepare_review_input**：验证普通问题会附加提示，代码块则原样返回
3. **run_shell**：验证不在白名单内的 shell 命令会被拒绝

涉及概念（面向小白）：
- ``@pytest.mark.asyncio``：标记异步测试，pytest 会用事件循环执行 ``async def`` 测试
- ``AsyncMock`` / ``patch``：unittest.mock 工具，用于模拟外部依赖（本文件部分测试未用到 mock）
- Pydantic 模型：用类型注解做数据校验；``model_json_schema()`` 可导出 JSON Schema
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.agents.code_reviewer import code_review_agent, prepare_review_input
from app.models.schemas import CodeReviewOutput, CodeIssue
from app.tools.file_tools import run_shell


class TestCodeReviewAgent:
    """代码审查 Agent 及其输出模型的测试。"""

    @pytest.mark.asyncio
    async def test_output_type_is_code_review_output(self):
        """Agent 声明的 output_type 应为 CodeReviewOutput。"""
        # pydantic-ai Agent 用 output_type 约束 LLM 返回的结构化类型
        assert code_review_agent.output_type == CodeReviewOutput

    @pytest.mark.asyncio
    async def test_output_schema_has_required_fields(self):
        """CodeReviewOutput 的 JSON Schema 应包含 summary、issues 等必填字段。"""
        schema = CodeReviewOutput.model_json_schema()
        required = schema.get("required", [])
        assert "summary" in required
        assert "issues" in required
        assert "quality_score" in required
        assert "approved" in required

    @pytest.mark.asyncio
    async def test_code_issue_validation(self):
        """合法 severity 的 CodeIssue 应能正常实例化。"""
        issue = CodeIssue(
            line=10,
            severity="warning",
            message="Unused variable",
            suggestion="Remove the variable or use it",
        )
        assert issue.severity == "warning"

    @pytest.mark.asyncio
    async def test_code_issue_invalid_severity(self):
        """当前 CodeIssue 未强制 severity 枚举，无效值也会通过（文档化现状）。"""
        # Pydantic 不强制枚举，但可以自定义验证器
        issue = CodeIssue(
            line=1,
            severity="invalid",
            message="test",
            suggestion="test",
        )
        # 默认通过，生产环境需加 validator
        # 本测试主要记录：无效 severity 目前不会抛错

    @pytest.mark.asyncio
    async def test_quality_score_range(self):
        """quality_score 应在 0–100 的合理区间内。"""
        output = CodeReviewOutput(
            summary="test",
            issues=[],
            quality_score=85,
            approved=True,
        )
        # 业务上分数是百分制
        assert 0 <= output.quality_score <= 100


class TestPrepareReviewInput:
    """prepare_review_input 输入预处理逻辑的测试。"""

    def test_general_question_gets_hint(self):
        """普通自然语言问题应附加「不要调用工具」类提示。"""
        result = prepare_review_input("springboot项目代码审查要注意哪些点？")
        # 提示文案里包含约束说明，避免 Agent 误调 shell 等工具
        assert "不要调用" in result

    def test_code_block_skips_hint(self):
        """输入已是 Markdown 代码块时，不应改写内容。"""
        code = "```java\npublic class App {}\n```"
        # 代码块视为「已是待审代码」，直接返回
        assert prepare_review_input(code) == code


class TestRunShell:
    """run_shell 工具的安全白名单测试。"""

    @pytest.mark.asyncio
    async def test_disallowed_command_returns_error_string(self):
        """不在白名单内的命令应返回错误说明，而非执行。"""
        result = await run_shell("which python")
        assert "not in allowlist" in result
        assert "which" in result
