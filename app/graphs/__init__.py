"""图编排包初始化 — 对外暴露工作流图和状态类型。

本包封装了基于 pydantic-graph 的多 Agent 协作逻辑。
其他模块（如 ``app.api.routes``）通过此处导入 ``agent_workflow`` 和 ``WorkflowState``，
无需直接依赖 ``workflow.py`` 的内部实现细节。

使用示例::

    from app.graphs import agent_workflow, WorkflowState
    from app.graphs.workflow import RouterNode

    state = WorkflowState(user_input="分析订单数据")
    result = await agent_workflow.run(start_node=RouterNode(), state=state)
"""

from app.graphs.workflow import agent_workflow, WorkflowState

# 公开 API：仅导出工作流图实例和状态类
__all__ = ["agent_workflow", "WorkflowState"]
