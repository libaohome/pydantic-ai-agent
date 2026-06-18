"""单元测试 — Gradio Agent 表单字段组装。"""

from __future__ import annotations

from app.ui.agent_forms import agent_form_visibility, build_agent_user_input


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


def test_build_chat_model_input():
    text, err = build_agent_user_input("chat-model", chat_input="你好")
    assert err is None
    assert text == "你好"


def test_build_image_gen_input():
    text, err = build_agent_user_input("image-gen", chat_input="画一只猫")
    assert err is None
    assert text == "画一只猫"


def test_build_chat_model_requires_input():
    _, err = build_agent_user_input("chat-model", chat_input="")
    assert err is not None


def test_agent_form_visibility():
    assert agent_form_visibility("chat-model") == (False, False, False, True, False)
    assert agent_form_visibility("image-gen") == (False, False, False, False, True)
    assert agent_form_visibility("qa-assistant") == (True, False, False, False, False)
