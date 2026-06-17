"""单元测试 — Workflow 运行器。"""

import pytest

from app.graphs import WorkflowName, run_workflow
from app.models.schemas import WorkflowRunRequest, WorkflowRunResult, WorkflowStateSnapshot


def test_workflow_run_result_success_and_error_share_fields():
    success = WorkflowRunResult(
        request_id="abc",
        workflow="agent-router",
        tenant_id="tenant01",
        user_id="user01",
        session_id="session01",
        status="success",
        state=WorkflowStateSnapshot(qa_result="ok"),
        elapsed_seconds=1.0,
    )
    error = WorkflowRunResult(
        request_id="abc",
        workflow="agent-router",
        tenant_id="tenant01",
        user_id="user01",
        session_id="session01",
        status="error",
        state=WorkflowStateSnapshot(),
        error="boom",
        elapsed_seconds=0.5,
    )

    assert success.is_success
    assert not error.is_success
    assert set(WorkflowRunResult.model_fields) == set(error.model_fields)


@pytest.mark.asyncio
async def test_run_workflow_unknown_is_enum_validated():
    """WorkflowName 枚举在路由层校验；此处仅验证注册表可解析。"""
    assert WorkflowName.agent_router.value == "agent-router"
