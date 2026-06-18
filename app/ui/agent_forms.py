"""Gradio Agent 测试表单 — 按 Agent 类型构建 user_input 与切换可见字段。"""

from __future__ import annotations

from app.models.schemas import CodeReviewInput, DataAnalysisInput, QaInput

LANGUAGE_CHOICES = [
    "python", "java", "kotlin", "go", "javascript", "typescript", "rust", "ruby", "sql", "other",
]

DOMAIN_CHOICES = ["general", "ai", "finance", "medical", "legal", "tech"]


def build_agent_user_input(
    agent_value: str,
    *,
    question: str = "",
    domain: str = "general",
    code: str = "",
    language: str = "python",
    context: str = "",
    query: str = "",
    data_source: str = "",
    chat_input: str = "",
) -> tuple[str, str | None]:
    """将各 Agent 的结构化字段组装为 ``user_input`` 文本。

    Returns:
        (user_input, error_message) — error_message 非空表示校验失败。
    """
    if agent_value == "code-reviewer":
        inp = CodeReviewInput(
            code=code.strip(),
            language=language or "python",
            context=context.strip(),
        )
        if not inp.code and not inp.context:
            return "", "请填写待审查代码或额外上下文"
        parts: list[str] = []
        if inp.context:
            parts.append(f"**审查上下文:** {inp.context}")
        if inp.code:
            lang = inp.language if inp.language != "other" else ""
            fence = lang or ""
            parts.append(f"请审查以下 {inp.language} 代码：\n\n```{fence}\n{inp.code}\n```")
        return "\n\n".join(parts), None

    if agent_value == "data-analyst":
        inp = DataAnalysisInput(
            query=query.strip(),
            data_source=data_source.strip() or "default",
        )
        if not inp.query:
            return "", "请填写分析需求"
        if inp.data_source and inp.data_source != "default":
            return f"**数据源:** {inp.data_source}\n\n**分析需求:**\n{inp.query}", None
        return inp.query, None

    if agent_value == "qa-assistant":
        inp = QaInput(question=question.strip(), domain=domain or "general")
        if not inp.question:
            return "", "请填写问题"
        if inp.domain and inp.domain != "general":
            return f"[领域: {inp.domain}]\n\n{inp.question}", None
        return inp.question, None

    if agent_value in ("chat-model", "image-gen"):
        text = chat_input.strip()
        if not text:
            label = "生图描述" if agent_value == "image-gen" else "消息"
            return "", f"请填写{label}"
        return text, None

    return "", f"未知 Agent: {agent_value}"


def agent_form_visibility(agent_value: str) -> tuple[bool, bool, bool, bool, bool]:
    """返回 (qa_visible, review_visible, analyst_visible, chat_model_visible, image_gen_visible)。"""
    return (
        agent_value == "qa-assistant",
        agent_value == "code-reviewer",
        agent_value == "data-analyst",
        agent_value == "chat-model",
        agent_value == "image-gen",
    )
