"""单元测试 — 图工作流"""

import pytest
from app.graphs.workflow import (
    agent_workflow, WorkflowState,
    RouterNode, AnalyzeNode, ReviewNode, QaNode,
    classify_route,
)


class TestWorkflow:

    def test_graph_has_all_nodes(self):
        node_names = set(agent_workflow.node_defs)
        assert "RouterNode" in node_names
        assert "AnalyzeNode" in node_names
        assert "ReviewNode" in node_names
        assert "QaNode" in node_names

    def test_workflow_state_defaults(self):
        state = WorkflowState()
        assert state.user_input == ""
        assert state.needs_review is False
        assert state.needs_qa is False

    def test_classify_route_analysis(self):
        assert classify_route("查询上个月的订单统计数据") == "analyze"

    def test_classify_route_weather_skill(self):
        assert classify_route("使用weather skill 查询北京明天天气怎么样？") == "qa"

    def test_classify_route_review(self):
        assert classify_route("帮我审查这段代码有没有 bug") == "review"

    def test_classify_route_image_forgery(self):
        assert classify_route(
            "使用 image-forgery-detector skills检测图片：https://example.com/a.png是否有伪造嫌疑"
        ) == "qa"
