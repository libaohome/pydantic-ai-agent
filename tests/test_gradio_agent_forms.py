"""单元测试 — Gradio Agent 表单字段组装。"""

from app.ui.agent_forms import build_agent_user_input


def test_build_qa_input():
    text, err = build_agent_user_input(
        "qa-assistant",
        question="什么是 RAG？",
        domain="ai",
    )
    assert err is None
    assert "[领域: ai]" in text
    assert "什么是 RAG？" in text


def test_build_qa_input_general_domain():
    text, err = build_agent_user_input("qa-assistant", question="你好")
    assert err is None
    assert text == "你好"


def test_build_code_review_input():
    text, err = build_agent_user_input(
        "code-reviewer",
        code="def div(a, b): return a/b",
        language="python",
        context="PR #1",
    )
    assert err is None
    assert "PR #1" in text
    assert "```python" in text
    assert "div(a, b)" in text


def test_build_code_review_requires_content():
    _, err = build_agent_user_input("code-reviewer", code="", context="")
    assert err is not None


def test_build_data_analyst_input():
    text, err = build_agent_user_input(
        "data-analyst",
        query="统计平均薪资",
        data_source="hr_db",
    )
    assert err is None
    assert "hr_db" in text
    assert "统计平均薪资" in text


def test_build_data_analyst_requires_query():
    _, err = build_agent_user_input("data-analyst", query="")
    assert err is not None
