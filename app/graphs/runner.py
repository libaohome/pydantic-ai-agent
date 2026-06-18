"""Workflow 运行器 — 统一的工作流执行入口与结果封装。"""

from __future__ import annotations

import time
import uuid

import logfire

from app.graphs.agent_router import RouterNode, WorkflowState
from app.graphs.registry import WorkflowName, get_workflow
from app.models.schemas import WorkflowRunRequest, WorkflowRunResult, WorkflowStateSnapshot

_STATE_PREVIEW_LIMIT = 500


async def run_workflow(workflow_name: WorkflowName, request: WorkflowRunRequest) -> WorkflowRunResult:
    """运行指定工作流并返回统一的 success/error 结构。"""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    graph = get_workflow(workflow_name)

    with logfire.span(
        "run_workflow",
        workflow=workflow_name.value,
        request_id=request_id,
        tenant_id=request.tenant_id,
        user_id=request.user_id,
        session_id=request.session_id,
    ):
        state = WorkflowState(
            user_input=request.user_input,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            session_id=request.session_id,
            file_ids=request.file_ids,
            runtime_config=request.runtime_config,
        )

        try:
            result = await graph.run(start_node=RouterNode(), state=state)
            workflow_state = result.state
            elapsed = round(time.time() - start_time, 3)
            snapshot = _snapshot_state(workflow_state)
            has_error = bool(workflow_state.error)

            return WorkflowRunResult(
                request_id=request_id,
                workflow=workflow_name.value,
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                session_id=request.session_id,
                status="error" if has_error else "success",
                state=snapshot,
                error=workflow_state.error or None,
                elapsed_seconds=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start_time, 3)
            logfire.error("workflow_run_failed", error=str(e), request_id=request_id)
            return WorkflowRunResult(
                request_id=request_id,
                workflow=workflow_name.value,
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                session_id=request.session_id,
                status="error",
                state=WorkflowStateSnapshot(),
                error=str(e),
                elapsed_seconds=elapsed,
            )


def _snapshot_state(state: WorkflowState) -> WorkflowStateSnapshot:
    def clip(value: str) -> str | None:
        if not value:
            return None
        return value[:_STATE_PREVIEW_LIMIT]

    return WorkflowStateSnapshot(
        analysis_result=clip(state.analysis_result),
        review_result=clip(state.review_result),
        qa_result=clip(state.qa_result),
        error=state.error or None,
    )
