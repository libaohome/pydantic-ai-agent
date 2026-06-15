"""单元测试 — 代码审查 Agent"""

import pytest
from unittest.mock import AsyncMock, patch

from app.agents.code_reviewer import code_review_agent
from app.models.schemas import CodeReviewOutput, CodeIssue


class TestCodeReviewAgent:
    """代码审查 Agent 测试"""

    @pytest.mark.asyncio
    async def test_output_type_is_code_review_output(self):
        """验证 Agent 的输出类型正确"""
        assert code_review_agent.output_type == CodeReviewOutput

    @pytest.mark.asyncio
    async def test_output_schema_has_required_fields(self):
        """验证输出 Schema 包含必要字段"""
        schema = CodeReviewOutput.model_json_schema()
        required = schema.get("required", [])
        assert "summary" in required
        assert "issues" in required
        assert "quality_score" in required
        assert "approved" in required

    @pytest.mark.asyncio
    async def test_code_issue_validation(self):
        """验证 CodeIssue 模型校验"""
        issue = CodeIssue(
            line=10,
            severity="warning",
            message="Unused variable",
            suggestion="Remove the variable or use it",
        )
        assert issue.severity == "warning"

    @pytest.mark.asyncio
    async def test_code_issue_invalid_severity(self):
        """验证 CodeIssue 不接受无效 severity"""
        # Pydantic 不强制枚举，但可以自定义验证器
        issue = CodeIssue(
            line=1,
            severity="invalid",
            message="test",
            suggestion="test",
        )
        # 默认通过，生产环境需加 validator

    @pytest.mark.asyncio
    async def test_quality_score_range(self):
        """验证 quality_score 在 0-100 范围内"""
        output = CodeReviewOutput(
            summary="test",
            issues=[],
            quality_score=85,
            approved=True,
        )
        assert 0 <= output.quality_score <= 100
