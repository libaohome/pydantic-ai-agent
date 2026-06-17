"""
Gradio Web 管理控制台模块。

在 FastAPI 应用上挂载一个可视化界面（默认路径 /ui），提供五个 Tab：

1. **Chat** — 与 ChatModelAgent 多轮对话（模型原生文本/多模态/生图能力）
2. **Agent** — 查看已注册 Agent 列表，并做单次测试调用
3. **Workflow** — 查看已注册 Workflow 列表，并做单次测试调用
4. **Model** — 展示模型注册表、API Key 状态与累计调用成本
5. **Skills** — 上传/卸载 Skill ZIP，查看已安装列表

技术栈：Gradio Blocks + 项目内已有的 run_agent / SkillPackageManager API。

面向小白：
- Gradio 用 Python 声明式构建网页 UI，无需写 HTML
- 事件绑定如 button.click(fn, inputs, outputs) 表示点击后调用 Python 函数
- Chatbot 使用 Gradio 6 的消息格式：list[dict]，每项含 role 与 content
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import gradio as gr
from fastapi import FastAPI

from app.agents.registry import AgentName, list_agents
from app.agents import run_agent
from app.graphs import WorkflowName, list_workflows, run_workflow
from app.agents.chat_media import format_chat_model_output_markdown
from app.core.config import get_settings
from app.core.llm import MODEL_REGISTRY, get_llm_manager
from app.core.uploads import get_upload_store
from app.models.schemas import AgentRunRequest, AgentRunResult, WorkflowRunRequest, WorkflowRunResult
from app.skills.routes import get_skill_manager
from app.ui.agent_forms import (
    DOMAIN_CHOICES,
    LANGUAGE_CHOICES,
    agent_form_visibility,
    build_agent_user_input,
)

# Gradio 6 Chatbot 单条消息与历史记录的类型别名
ChatMessage = dict[str, str]
ChatHistory = list[ChatMessage]
CHATBOT_HEIGHT = 420
MultimodalInput = str | dict[str, Any] | None
EMPTY_MULTIMODAL_INPUT: dict[str, str | list] = {"text": "", "files": []}

# 下拉框显示名 → 内部 agent 标识（不含 workflow）
AGENT_CHOICES: list[tuple[str, str]] = [
    ("知识问答 (qa-assistant)", "qa-assistant"),
    ("代码审查 (code-reviewer)", "code-reviewer"),
    ("数据分析 (data-analyst)", "data-analyst"),
]

# 模型别名列表，来自 LLM 注册表
MODEL_CHOICES: list[str] = list(MODEL_REGISTRY.keys())

# 反向映射：界面标签 → agent value
AGENT_LABELS = {label: value for label, value in AGENT_CHOICES}

GradioUpdate = dict[str, Any]


def _workflow_choices() -> list[tuple[str, str]]:
    """下拉框显示名 → 内部 workflow 标识。"""
    return [
        (f"{item['description']} ({item['name']})", item["name"])
        for item in list_workflows()
    ]


def _workflow_labels() -> dict[str, str]:
    return {label: value for label, value in _workflow_choices()}

logger = logging.getLogger(__name__)


# ─── 格式化工具 ──────────────────────────────────

def _format_agent_output(output: Any, agent: str) -> str:
    """
    将各 Agent 的结构化输出 dict 转成易读的 Markdown 文本。

    不同 agent 的 output 字段不同，此处按类型分别排版。
    """
    if not isinstance(output, dict):
        return str(output)

    if agent == "chat-model":
        return format_chat_model_output_markdown(output)

    if agent == "qa-assistant":
        lines = [output.get("answer", "")]
        confidence = output.get("confidence")
        if confidence is not None:
            lines.append(f"\n**置信度:** {confidence:.0%}")
        sources = output.get("sources") or []
        if sources:
            lines.append("\n**参考来源:**")
            for src in sources:
                title = src.get("title", "")
                url = src.get("url", "")
                lines.append(f"- [{title}]({url})" if url else f"- {title}")
        follow_ups = output.get("follow_ups") or []
        if follow_ups:
            lines.append("\n**追问建议:** " + " · ".join(follow_ups))
        return "\n".join(lines)

    if agent == "code-reviewer":
        lines = [
            f"**总结:** {output.get('summary', '')}",
            f"**质量评分:** {output.get('quality_score', 'N/A')} | "
            f"**通过:** {'✅' if output.get('approved') else '❌'}",
        ]
        issues = output.get("issues") or []
        if issues:
            lines.append("\n**问题列表:**")
            for issue in issues:
                line = issue.get("line", 0)
                line_str = "通用" if line == 0 else f"L{line}"
                lines.append(
                    f"- {line_str} [{issue.get('severity', '')}] "
                    f"{issue.get('message', '')} → {issue.get('suggestion', '')}"
                )
        return "\n".join(lines)

    if agent == "data-analyst":
        lines = [f"**分析结论:**\n{output.get('analysis', '')}"]
        if output.get("sql_query"):
            lines.append(f"\n**SQL:** `{output['sql_query']}`")
        recs = output.get("recommendations") or []
        if recs:
            lines.append("\n**建议:**\n" + "\n".join(f"- {r}" for r in recs))
        charts = output.get("charts") or []
        if charts:
            lines.append(f"\n**图表:** {len(charts)} 个")
        return "\n".join(lines)

    # 未知 agent 类型：原样 JSON 展示
    return f"```json\n{json.dumps(output, ensure_ascii=False, indent=2)}\n```"


def _format_run_meta(result: AgentRunResult) -> str:
    """在回复末尾附加请求元信息：request_id、耗时、token、费用。"""
    return (
        f"\n\n---\n"
        f"*request_id: {result.request_id} | "
        f"session: {result.session_id} | "
        f"耗时: {result.elapsed_seconds}s | "
        f"tokens: {result.usage.request_tokens}+{result.usage.response_tokens} | "
        f"cost: ${result.cost_usd:.6f}*"
    )


def _append_chat_turn(history: ChatHistory, user: str, assistant: str) -> ChatHistory:
    """向 Chatbot 历史追加一轮 user/assistant 消息。"""
    return [
        *history,
        {"role": "user", "content": user},
        {"role": "assistant", "content": assistant},
    ]


def _format_agent_test_user_message(
    agent_label: str,
    model_alias: str | None,
    user_input: str,
) -> str:
    model = model_alias or "（默认）"
    return f"**Agent:** {agent_label} | **模型:** `{model}`\n\n{user_input}"


def _format_workflow_test_user_message(
    workflow_label: str,
    session_id: str,
    test_input: str,
) -> str:
    session = (session_id or "").strip() or "session01"
    return f"**Workflow:** {workflow_label} | **会话:** `{session}`\n\n{test_input}"


def _resolve_gradio_file_ref(item: Any) -> tuple[str, str] | None:
    """从 Gradio MultimodalTextbox 的 files 项解析本地路径与原始文件名。

    Gradio 6 preprocess 后 files 通常是路径字符串列表，而非 dict。
    """
    path: str | None = None
    orig_name: str | None = None

    if isinstance(item, str):
        path = item
    elif isinstance(item, dict):
        path = item.get("path") or item.get("url")
        orig_name = item.get("orig_name")
    else:
        path = getattr(item, "path", None) or getattr(item, "url", None)
        orig_name = getattr(item, "orig_name", None)

    if not path:
        return None

    local = Path(path)
    if not local.is_file():
        local = local.resolve()
    if not local.is_file():
        logger.warning("Gradio upload path is not a readable file: %s", path)
        return None

    return str(local), orig_name or local.name


def _save_multimodal_uploads(value: MultimodalInput) -> tuple[str, list[str]]:
    """解析 MultimodalTextbox 输入，将附件保存到 data/upload 并返回 file_id 列表。"""
    if value is None:
        return "", []
    if isinstance(value, str):
        return value.strip(), []

    text = str(value.get("text") or "").strip()
    raw_files = value.get("files") or []
    store = get_upload_store()
    file_ids: list[str] = []

    for item in raw_files:
        resolved = _resolve_gradio_file_ref(item)
        if not resolved:
            continue
        path, orig_name = resolved
        try:
            file_ids.append(store.save_from_path(path, orig_name))
        except (FileNotFoundError, OSError) as e:
            logger.warning("Failed to persist upload %s: %s", path, e)

    return text, file_ids


def _format_user_message(text: str, file_ids: list[str]) -> str:
    """在对话历史中展示用户消息（含附件摘要）。"""
    if not file_ids:
        return text

    store = get_upload_store()
    names: list[str] = []
    for file_id in file_ids:
        try:
            names.append(store.get_metadata(file_id).original_name)
        except FileNotFoundError:
            names.append(file_id)

    attachment = ", ".join(names)
    if text:
        return f"{text}\n\n📎 附件: {attachment}"
    return f"📎 附件: {attachment}"


def _format_workflow_result(result: WorkflowRunResult) -> str:
    """将 Workflow 运行结果格式化为 Markdown。"""
    ws = result.state
    parts: list[str] = []
    if ws.qa_result:
        parts.append(f"**问答结果:**\n{ws.qa_result}")
    if ws.review_result:
        parts.append(f"**审查结果:**\n{ws.review_result}")
    if ws.analysis_result:
        parts.append(f"**分析结果:**\n{ws.analysis_result}")
    if ws.error:
        parts.append(f"**错误:** {ws.error}")
    body = "\n\n".join(parts) if parts else "工作流未产生输出"
    return (
        f"{body}\n\n---\n"
        f"*request_id: {result.request_id} | session: {result.session_id} | "
        f"耗时: {result.elapsed_seconds}s | 模式: 自动路由*"
    )


async def _run_chat_agent(
    message: str,
    agent_value: str,
    model_alias: str | None,
    file_ids: list[str] | None = None,
    session_id: str | None = None,
) -> str:
    """
    执行一次 Chat/Agent 调用，返回 Markdown 字符串。

    参数:
            message: 用户输入
            agent_value: 内部 agent 名（如 qa-assistant）
            model_alias: 模型别名，None 则用各 Agent 默认模型
            file_ids: 可选的上传文件 ID 列表
            session_id: 会话名称，对应 UI「会话名称」输入框

    workflow 模式已移至 Workflow Tab；此处仅调用 run_agent。
    """
    model = model_alias if model_alias else None
    ids = file_ids or []
    session = (session_id or "").strip() or "session01"

    agent_name = AgentName(agent_value)
    result = await run_agent(
        agent_name,
        AgentRunRequest(
            user_input=message,
            session_id=session,
            model_alias=model,
            file_ids=ids,
        ),
    )
    if not result.is_success:
        return f"❌ **错误:** {result.error}{_format_run_meta(result)}"

    output = result.output
    body = _format_agent_output(output, agent_value)
    return f"{body}{_format_run_meta(result)}"


# ─── Skills 管理 ─────────────────────────────────

def _skills_to_markdown() -> str:
    """将已安装 Skill 列表格式化为 Markdown 表格。"""
    try:
        manager = get_skill_manager()
        result = manager.list_installed()
    except Exception as e:
        return f"⚠️ 无法加载 Skills: {e}"

    if result.total == 0:
        return "*暂无已安装的 Skill*"

    lines = ["| 名称 | 版本 | 作者 | 分类 | 上传时间 | 脚本 | 资源 |",
                      "|------|------|------|------|----------|------|------|"]
    for s in result.skills:
        lines.append(
            f"| {s.name} | {s.version} | {s.author} | {s.category} | "
            f"{s.uploaded_at[:10]} | {'✓' if s.has_scripts else '-'} | "
            f"{'✓' if s.has_resources else '-'} |"
        )
    lines.append(f"\n**共 {result.total} 个 Skill** · 目录: `{manager.get_skills_directory()}`")
    return "\n".join(lines)


def _skill_names() -> list[str]:
    """返回已安装 Skill 的 name 列表，供下拉框使用。"""
    try:
        manager = get_skill_manager()
        return [s.name for s in manager.list_installed().skills]
    except Exception:
        return []


def _skill_dropdown_update() -> GradioUpdate:
    """生成 Gradio Dropdown 的 update 对象，刷新选项列表。"""
    return gr.update(choices=_skill_names(), value=None)


async def upload_skill_file(
    file: str | None,
    uploaded_by: str,
    allow_warnings: bool,
) -> tuple[str, str, gr.Dropdown]:
    """
    Gradio 上传 Skill ZIP 的回调。

    参数 file 为 Gradio File 组件返回的本地临时路径字符串。
    返回: (状态消息, 列表 Markdown, 卸载下拉框更新)
    """
    if not file:
        return "请选择 ZIP 文件", _skills_to_markdown(), _skill_dropdown_update()

    zip_path = Path(file)
    if zip_path.suffix.lower() != ".zip":
        return "仅支持 .zip 文件", _skills_to_markdown(), _skill_dropdown_update()

    zip_bytes = zip_path.read_bytes()
    manager = get_skill_manager()
    result = await manager.upload(
        zip_bytes=zip_bytes,
        uploaded_by=uploaded_by or "gradio-ui",
        allow_warnings=allow_warnings,
    )

    if result.success:
        msg = f"✅ {result.message} (v{result.version}, {result.file_count} 文件)"
        if result.warnings:
            msg += "\n\n⚠️ 警告:\n" + "\n".join(f"- {w}" for w in result.warnings)
    else:
        msg = f"❌ {result.message}"

    return msg, _skills_to_markdown(), _skill_dropdown_update()


def uninstall_skill(skill_name: str | None) -> tuple[str, str, gr.Dropdown]:
    """Gradio 卸载 Skill 的回调。"""
    if not skill_name:
        return "请选择要卸载的 Skill", _skills_to_markdown(), _skill_dropdown_update()

    manager = get_skill_manager()
    try:
        success = manager.uninstall(skill_name)
    except ValueError as e:
        return f"❌ {e}", _skills_to_markdown(), _skill_dropdown_update()

    if success:
        msg = f"✅ Skill '{skill_name}' 已卸载"
    else:
        msg = f"❌ Skill '{skill_name}' 不存在"

    return msg, _skills_to_markdown(), _skill_dropdown_update()


def refresh_skills() -> tuple[str, gr.Dropdown]:
    """刷新 Skill 列表与卸载下拉框。"""
    return _skills_to_markdown(), _skill_dropdown_update()


# ─── Model 管理 ──────────────────────────────────

def _models_to_dataframe() -> list[list[str]]:
    """将 MODEL_REGISTRY 转为 Gradio Dataframe 所需的二维列表。"""
    llm = get_llm_manager()
    rows: list[list[str]] = []
    for alias, cfg in MODEL_REGISTRY.items():
        rows.append([
            alias,
            cfg.provider,
            cfg.model_id,
            llm._get_base_url(cfg.credential_group) if cfg.credential_group else "-",
            "是" if cfg.reasoning else "否",
            "是" if cfg.multimodal else "否",
            "是" if cfg.image_generation else "否",
            f"${cfg.cost_per_1m_input:.2f}",
            f"${cfg.cost_per_1m_output:.2f}",
        ])
    return rows


def refresh_models() -> tuple[list[list[str]], str, str]:
    """
    刷新模型表格、累计成本 Markdown、默认模型信息。

    在 Tab 加载和点击「刷新」时调用。
    """
    get_settings.cache_clear()
    llm = get_llm_manager()
    settings = get_settings()
    costs = llm.get_cost_report()

    if costs:
        cost_lines = "\n".join(f"- **{k}:** ${v:.6f}" for k, v in costs.items())
        cost_md = f"### 累计成本\n{cost_lines}\n\n**总计:** ${sum(costs.values()):.6f}"
    else:
        cost_md = "### 累计成本\n*暂无调用记录*"

    default_info = (
        f"**默认模型:** `{settings.default_model}`\n\n"
        f"**环境:** `{settings.app_env}`"
    )
    return _models_to_dataframe(), cost_md, default_info


# ─── Agent 管理 ──────────────────────────────────

def _agents_to_markdown() -> str:
    """将 list_agents() 结果格式化为 Markdown 表格。"""
    agents = list_agents()
    lines = ["| Agent | 当前模型 | 输出类型 |",
                      "|-------|----------|----------|"]
    for a in agents:
        lines.append(f"| {a['name']} | `{a['model']}` | {a['output_type']} |")
    return "\n".join(lines)


async def run_agent_test(
    agent_label: str,
    model_alias: str | None,
    question: str,
    domain: str,
    code: str,
    language: str,
    context: str,
    query: str,
    data_source: str,
    history: ChatHistory,
) -> ChatHistory:
    """
    Agent 测试 Tab 的运行按钮回调。

    根据所选 Agent 读取对应结构化字段，组装为 user_input 后调用 run_agent。
    """
    agent_value = AGENT_LABELS.get(agent_label, "qa-assistant")
    user_input, err = build_agent_user_input(
        agent_value,
        question=question,
        domain=domain,
        code=code,
        language=language,
        context=context,
        query=query,
        data_source=data_source,
    )
    if err:
        return _append_chat_turn(
            history,
            _format_agent_test_user_message(agent_label, model_alias, "（输入校验失败）"),
            f"⚠️ {err}",
        )

    agent_name = AgentName(agent_value)
    result = await run_agent(
        agent_name,
        AgentRunRequest(
            user_input=user_input,
            model_alias=model_alias if model_alias else None,
        ),
    )
    user_message = _format_agent_test_user_message(agent_label, model_alias, user_input)
    if not result.is_success:
        err_json = json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
        return _append_chat_turn(
            history,
            user_message,
            f"❌ {result.error}\n\n```json\n{err_json}\n```",
        )

    formatted = _format_agent_output(result.output, agent_value)
    return _append_chat_turn(history, user_message, f"{formatted}{_format_run_meta(result)}")


def switch_agent_input_form(agent_label: str) -> tuple[gr.update, gr.update, gr.update]:
    """切换 Agent 输入区各字段分组的可见性（Chat / Agent 测试共用）。"""
    agent_value = AGENT_LABELS.get(agent_label, "qa-assistant")
    show_qa, show_review, show_analyst = agent_form_visibility(agent_value)
    return (
        gr.update(visible=show_qa),
        gr.update(visible=show_review),
        gr.update(visible=show_analyst),
    )


# 保持旧名称兼容测试/引用
switch_agent_test_form = switch_agent_input_form


# ─── Workflow 管理 ───────────────────────────────

def _workflows_to_markdown() -> str:
    """将 list_workflows() 结果格式化为 Markdown 表格。"""
    workflows = list_workflows()
    lines = ["| Workflow | 说明 |", "|----------|------|"]
    for item in workflows:
        lines.append(f"| {item['name']} | {item['description']} |")
    return "\n".join(lines)


async def run_workflow_test(
    workflow_label: str,
    test_input: str,
    session_id: str,
    history: ChatHistory,
) -> ChatHistory:
    """Workflow 测试 Tab 的运行按钮回调。"""
    if not test_input.strip():
        return _append_chat_turn(
            history,
            _format_workflow_test_user_message(workflow_label, session_id, "（空输入）"),
            "⚠️ 请输入测试内容",
        )

    labels = _workflow_labels()
    workflow_value = labels.get(workflow_label, WorkflowName.agent_router.value)
    session = (session_id or "").strip() or "session01"
    user_message = _format_workflow_test_user_message(workflow_label, session_id, test_input)

    result = await run_workflow(
        WorkflowName(workflow_value),
        WorkflowRunRequest(user_input=test_input, session_id=session),
    )
    if not result.is_success:
        err_json = json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
        return _append_chat_turn(
            history,
            user_message,
            f"❌ {result.error}\n\n```json\n{err_json}\n```",
        )

    return _append_chat_turn(history, user_message, _format_workflow_result(result))


def clear_agent_test_history() -> ChatHistory:
    return []


def clear_workflow_test_history() -> ChatHistory:
    return []


# ─── Chat 管理 ───────────────────────────────────

async def chat_submit(
    message: MultimodalInput,
    history: ChatHistory,
    model_alias: str | None,
    session_name: str,
) -> tuple[ChatHistory, MultimodalInput]:
    """发送聊天消息（ChatModelAgent），追加对话记录并清空输入框。"""
    text, file_ids = _save_multimodal_uploads(message)
    if not text and not file_ids:
        return history, EMPTY_MULTIMODAL_INPUT

    reply = await _run_chat_agent(
        text,
        AgentName.chat_model.value,
        model_alias,
        file_ids=file_ids,
        session_id=session_name,
    )
    display_message = _format_user_message(text, file_ids)
    history = [
        *history,
        {"role": "user", "content": display_message},
        {"role": "assistant", "content": reply},
    ]
    return history, EMPTY_MULTIMODAL_INPUT


def clear_chat() -> tuple[ChatHistory, MultimodalInput, str]:
    """清空对话历史与导出框。"""
    return [], EMPTY_MULTIMODAL_INPUT, ""


def export_chat(history: ChatHistory, session_name: str) -> str:
    """将当前对话导出为 JSON 字符串。"""
    payload = {
        "session": session_name or "session01",
        "messages": history,
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ─── UI 构建 ─────────────────────────────────────

def create_gradio_demo() -> gr.Blocks:
    """
    构建完整的 Gradio Blocks 界面。

    返回:
            未 launch 的 gr.Blocks 实例，由 mount_gradio_ui 挂载到 FastAPI
    """
    with gr.Blocks(title="Pydantic AI Agent Console") as demo:
        gr.Markdown(
            "# 🤖 Pydantic AI Agent Console\n"
            "Chat · Agent · Workflow · Model · Skills 统一管理界面"
        )

        with gr.Tabs():
            # ── Chat Tab：多轮对话（qa-assistant + 模型切换）──
            with gr.Tab("💬 Chat"):
                gr.Markdown(
                    "与 **chat-model** 对话：纯模型原生能力（文本 / 多模态理解 / 生图），"
                    "不调用 Skill 或知识库。测试业务 Agent 请使用 **Agent** 标签页。"
                )
                with gr.Row():
                    chat_model = gr.Dropdown(
                        choices=MODEL_CHOICES,
                        value=MODEL_CHOICES[0],
                        label="模型",
                        allow_custom_value=False,
                    )
                    session_name = gr.Textbox(
                        label="会话名称",
                        placeholder="session01",
                        scale=1,
                    )
                chatbot = gr.Chatbot(label="对话", height=CHATBOT_HEIGHT, type="messages")
                with gr.Row():
                    chat_input = gr.MultimodalTextbox(
                        label="输入消息",
                        placeholder="输入问题或指令，可上传附件...",
                        file_types=[
                            ".py", ".java", ".kt", ".go", ".js", ".ts", ".txt", ".md",
                            ".json", ".csv", ".xml", ".yaml", ".yml", ".sql", ".png",
                            ".jpg", ".jpeg", ".webp", ".zip",
                        ],
                        file_count="multiple",
                        sources=["upload"],
                        submit_btn=False,
                        scale=4,
                    )
                    chat_send = gr.Button("发送", variant="primary", scale=1)
                with gr.Row():
                    chat_clear = gr.Button("清空对话")
                    chat_export = gr.Button("导出历史")
                chat_export_box = gr.Textbox(
                    label="导出 JSON",
                    lines=8,
                    visible=False,
                )

                chat_send.click(
                    chat_submit,
                    inputs=[chat_input, chatbot, chat_model, session_name],
                    outputs=[chatbot, chat_input],
                )
                chat_input.submit(
                    chat_submit,
                    inputs=[chat_input, chatbot, chat_model, session_name],
                    outputs=[chatbot, chat_input],
                )
                chat_clear.click(clear_chat, outputs=[chatbot, chat_input, chat_export_box])
                chat_export.click(
                    export_chat,
                    inputs=[chatbot, session_name],
                    outputs=[chat_export_box],
                ).then(lambda: gr.update(visible=True), outputs=[chat_export_box])

            # ── Agent Tab：列表与单次测试 ──
            with gr.Tab("🤖 Agent"):
                gr.Markdown("### 已注册 Agent")
                agent_table = gr.Markdown(value=_agents_to_markdown())
                agent_refresh = gr.Button("刷新列表")
                agent_refresh.click(lambda: _agents_to_markdown(), outputs=[agent_table])

                gr.Markdown("### Agent 测试")
                with gr.Row():
                    test_agent = gr.Dropdown(
                        choices=[label for label, _ in AGENT_CHOICES],
                        value=AGENT_CHOICES[0][0],
                        label="选择 Agent",
                    )
                    test_model = gr.Dropdown(
                        choices=MODEL_CHOICES,
                        value=MODEL_CHOICES[0],
                        label="模型",
                    )

                with gr.Group(visible=True) as qa_input_group:
                    gr.Markdown("**知识问答** — 对应 `QaInput`")
                    test_question = gr.Textbox(
                        label="问题 (question)",
                        lines=3,
                        placeholder="例如：什么是 RAG 技术？",
                    )
                    test_domain = gr.Dropdown(
                        choices=DOMAIN_CHOICES,
                        value="general",
                        label="领域 (domain)",
                    )

                with gr.Group(visible=False) as review_input_group:
                    gr.Markdown("**代码审查** — 对应 `CodeReviewInput`")
                    test_code = gr.Textbox(
                        label="源代码 (code)",
                        lines=10,
                        placeholder="粘贴待审查的代码",
                    )
                    with gr.Row():
                        test_language = gr.Dropdown(
                            choices=LANGUAGE_CHOICES,
                            value="python",
                            label="编程语言 (language)",
                        )
                    test_context = gr.Textbox(
                        label="额外上下文 (context)",
                        lines=2,
                        placeholder="例如：PR #42 新增数学工具函数",
                    )

                with gr.Group(visible=False) as analyst_input_group:
                    gr.Markdown("**数据分析** — 对应 `DataAnalysisInput`")
                    test_query = gr.Textbox(
                        label="分析需求 (query)",
                        lines=3,
                        placeholder="例如：统计每个部门的平均薪资",
                    )
                    test_data_source = gr.Textbox(
                        label="数据源 (data_source)",
                        placeholder="例如：hr_db",
                    )

                test_run = gr.Button("运行测试", variant="primary")
                test_output = gr.Chatbot(label="测试记录", height=CHATBOT_HEIGHT, type="messages")
                test_clear = gr.Button("清空记录")

                test_agent.change(
                    switch_agent_input_form,
                    inputs=[test_agent],
                    outputs=[qa_input_group, review_input_group, analyst_input_group],
                )
                test_run.click(
                    run_agent_test,
                    inputs=[
                        test_agent,
                        test_model,
                        test_question,
                        test_domain,
                        test_code,
                        test_language,
                        test_context,
                        test_query,
                        test_data_source,
                        test_output,
                    ],
                    outputs=[test_output],
                )
                test_clear.click(clear_agent_test_history, outputs=[test_output])

            # ── Workflow Tab：列表与单次测试 ──
            with gr.Tab("🔀 Workflow"):
                gr.Markdown("### 已注册 Workflow")
                workflow_table = gr.Markdown(value=_workflows_to_markdown())
                workflow_refresh = gr.Button("刷新列表")
                workflow_refresh.click(lambda: _workflows_to_markdown(), outputs=[workflow_table])

                gr.Markdown("### Workflow 测试")
                workflow_choice_list = _workflow_choices()
                with gr.Row():
                    test_workflow = gr.Dropdown(
                        choices=[label for label, _ in workflow_choice_list],
                        value=workflow_choice_list[0][0] if workflow_choice_list else None,
                        label="选择 Workflow",
                    )
                    test_workflow_session = gr.Textbox(
                        label="会话名称",
                        placeholder="session01",
                        scale=1,
                    )
                test_workflow_input = gr.Textbox(
                    label="测试输入",
                    lines=4,
                    placeholder="输入测试内容，例如：帮我审查这段代码有没有 bug",
                )
                test_workflow_run = gr.Button("运行测试", variant="primary")
                test_workflow_output = gr.Chatbot(label="测试记录", height=CHATBOT_HEIGHT, type="messages")
                test_workflow_clear = gr.Button("清空记录")

                test_workflow_run.click(
                    run_workflow_test,
                    inputs=[
                        test_workflow,
                        test_workflow_input,
                        test_workflow_session,
                        test_workflow_output,
                    ],
                    outputs=[test_workflow_output],
                )
                test_workflow_clear.click(clear_workflow_test_history, outputs=[test_workflow_output])

            # ── Model Tab：注册表与成本 ──
            with gr.Tab("🧠 Model"):
                gr.Markdown("### 模型注册表")
                model_headers = [
                    "别名", "Provider", "Model ID", "Base URL",
                    "推理", "多模态", "文生图", "输入$/1M", "输出$/1M",
                ]
                model_table = gr.Dataframe(
                    headers=model_headers,
                    value=_models_to_dataframe(),
                    interactive=False,
                )
                model_cost = gr.Markdown()
                model_info = gr.Markdown()
                model_refresh = gr.Button("刷新", variant="primary")

                model_refresh.click(
                    refresh_models,
                    outputs=[model_table, model_cost, model_info],
                )
                demo.load(refresh_models, outputs=[model_table, model_cost, model_info])

            # ── Skills Tab：上传与卸载 ──
            with gr.Tab("📦 Skills"):
                gr.Markdown("### 已安装 Skills")
                skills_list = gr.Markdown(value=_skills_to_markdown())
                skills_refresh = gr.Button("刷新列表")

                gr.Markdown("### 上传 Skill ZIP")
                with gr.Row():
                    skill_file = gr.File(label="ZIP 文件", file_types=[".zip"])
                    skill_uploader = gr.Textbox(label="上传者", value="gradio-ui")
                    skill_allow_warn = gr.Checkbox(label="允许安全警告", value=True)
                skill_upload_btn = gr.Button("上传", variant="primary")
                skill_upload_msg = gr.Markdown()

                gr.Markdown("### 卸载 Skill")
                with gr.Row():
                    skill_uninstall_select = gr.Dropdown(
                        choices=_skill_names(),
                        label="选择 Skill",
                        allow_custom_value=False,
                    )
                    skill_uninstall_btn = gr.Button("卸载", variant="stop")
                skill_uninstall_msg = gr.Markdown()

                skills_refresh.click(refresh_skills, outputs=[skills_list, skill_uninstall_select])
                skill_upload_btn.click(
                    upload_skill_file,
                    inputs=[skill_file, skill_uploader, skill_allow_warn],
                    outputs=[skill_upload_msg, skills_list, skill_uninstall_select],
                )
                skill_uninstall_btn.click(
                    uninstall_skill,
                    inputs=[skill_uninstall_select],
                    outputs=[skill_uninstall_msg, skills_list, skill_uninstall_select],
                )
                demo.load(refresh_skills, outputs=[skills_list, skill_uninstall_select])

        gr.Markdown(
            "---\n"
            "[API 文档](/docs) · [健康检查](/health) · "
            "Powered by FastAPI + Pydantic AI + Gradio"
        )

    return demo


def mount_gradio_ui(app: FastAPI, path: str = "/ui") -> FastAPI:
    """
    将 Gradio 界面挂载到已有 FastAPI 应用指定路径。

    参数:
            app: FastAPI 实例
            path: URL 前缀，默认 /ui

    返回:
            挂载后的 FastAPI 应用（同一对象，便于链式调用）
    """
    demo = create_gradio_demo()
    return gr.mount_gradio_app(app, demo, path=path)
