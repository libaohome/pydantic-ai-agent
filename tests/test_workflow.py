"""单元测试 — 图工作流（LangGraph / pydantic-graph）。

测试目的：
- 确认工作流图包含 Router、Analyze、Review、Qa 四个节点
- 确认 ``WorkflowState`` 默认值符合预期
- 确认 ``classify_route`` 能根据用户输入关键词路由到正确分支

路由规则（被测函数 ``classify_route``）：
- 含「审查」「review」等 → ``review``
- 含「分析」「统计」「查询」等 → ``analyze``
- 含 skill 名称或 QA 相关 → ``qa``
"""

from __future__ import annotations

import pytest
from app.graphs.agent_router import (
    AnalyzeNode,
    QaNode,
    ReviewNode,
    RouterNode,
    WorkflowState,
    agent_router_workflow,
    classify_route,
)

# 兼容旧测试/导入名称
agent_workflow = agent_router_workflow


class TestWorkflow:
    """Agent 工作流图与路由逻辑的测试。"""

    def test_graph_has_all_nodes(self):
        """工作流图应注册 Router、Analyze、Review、Qa 四个节点。"""
        # node_defs 是图中所有节点定义的集合
        node_names = set(agent_router_workflow.node_defs)
        assert "RouterNode" in node_names
        assert "AnalyzeNode" in node_names
        assert "ReviewNode" in node_names
        assert "QaNode" in node_names

    def test_workflow_state_defaults(self):
        """新建 WorkflowState 时，各字段应有安全的默认值。"""
        state = WorkflowState()
        assert state.user_input == ""
        assert state.needs_review is False
        assert state.needs_qa is False

    def test_classify_route_analysis(self):
        """含「统计」「查询」类表述应路由到 analyze 分支。"""
        assert classify_route("查询上个月的订单统计数据") == "analyze"

    def test_classify_route_weather_skill(self):
        """提及 weather skill 的天气问题应路由到 qa 分支。"""
        assert classify_route("使用weather skill 查询北京明天天气怎么样？") == "qa"

    def test_classify_route_review(self):
        """代码审查类请求应路由到 review 分支。"""
        assert classify_route("帮我审查这段代码有没有 bug") == "review"

    def test_classify_route_image_forgery(self):
        """使用 image-forgery-detector skill 的请求应路由到 qa 分支。"""
        assert classify_route(
            "使用 image-forgery-detector skills检测图片：https://example.com/a.png是否有伪造嫌疑"
        ) == "qa"
