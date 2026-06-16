"""
Gradio Web 管理控制台模块。

在 FastAPI 应用上挂载一个可视化界面（默认路径 /ui），提供四个 Tab：

1. **Chat** — 与各类 Agent 对话，支持选择模型与会话导出
2. **Agent** — 查看已注册 Agent 列表，并做单次测试调用
3. **Model** — 展示模型注册表、API Key 状态与累计调用成本
4. **Skills** — 上传/卸载 Skill ZIP，查看已安装列表

技术栈：Gradio Blocks + 项目内已有的 _run_agent / SkillPackageManager API。

面向小白：
- Gradio 用 Python 声明式构建网页 UI，无需写 HTML
- 事件绑定如 button.click(fn, inputs, outputs) 表示点击后调用 Python 函数
- Chatbot 使用 Gradio 6 的消息格式：list[dict]，每项含 role 与 content
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import gradio as gr
from fastapi import FastAPI

from app.agents.registry import AgentName, list_agents
from app.api.routes import _run_agent
from app.core.config import get_settings
from app.core.llm import MODEL_REGISTRY, get_llm_manager
from app.core.uploads import get_upload_store
from app.graphs.workflow import RouterNode, WorkflowState, agent_workflow
from app.skills.routes import get_skill_manager

# Gradio 6 Chatbot 单条消息与历史记录的类型别名
ChatMessage = dict[str, str]
ChatHistory = list[ChatMessage]
MultimodalInput = str | dict[str, Any] | None
EMPTY_MULTIMODAL_INPUT: dict[str, str | list] = {"text": "", "files": []}

# 下拉框显示名 → 内部 agent 标识
AGENT_CHOICES: list[tuple[str, str]] = [
    ("知识问答 (qa-assistant)", "qa-assistant"),
    ("代码审查 (code-reviewer)", "code-reviewer"),
    ("数据分析 (data-analyst)", "data-analyst"),
    ("自动路由 (workflow)", "workflow"),
]

# 模型别名列表，来自 LLM 注册表
MODEL_CHOICES: list[str] = list(MODEL_REGISTRY.keys())

# 反向映射：界面标签 → agent value
AGENT_LABELS = {label: value for label, value in AGENT_CHOICES}

logger = logging.getLogger(__name__)


# ─── 格式化工具 ──────────────────────────────────

def _format_agent_output(output: Any, agent: str) -> str:
    """
    将各 Agent 的结构化输出 dict 转成易读的 Markdown 文本。

    不同 agent 的 output 字段不同，此处按类型分别排版。
    """
    if not isinstance(output, dict):
        return str(output)

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


def _format_run_meta(result: dict[str, Any]) -> str:
    """
    在回复末尾附加请求元信息：request_id、耗时、token、费用。
    """
    usage = result.get("usage") or {}
    return (
        f"\n\n---\n"
        f"*request_id: {result.get('request_id')} | "
        f"耗时: {result.get('elapsed_seconds')}s | "
        f"tokens: {usage.get('request_tokens', 0)}+{usage.get('response_tokens', 0)} | "
        f"cost: ${result.get('cost_usd', 0):.6f}*"
    )


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


async def _run_chat_agent(
    message: str,
    agent_value: str,
    model_alias: str | None,
    file_ids: list[str] | None = None,
) -> str:
    """
    执行一次 Chat/Agent 调用，返回 Markdown 字符串。

    参数:
            message: 用户输入
            agent_value: 内部 agent 名或 "workflow"
            model_alias: 模型别名，None 则用各 Agent 默认模型
            file_ids: 可选的上传文件 ID 列表

    workflow 模式走 LangGraph 工作流，其余走 _run_agent。
    """
    model = model_alias if model_alias else None
    ids = file_ids or []

    if agent_value == "workflow":
        start = time.time()
        state = WorkflowState(user_input=message, file_ids=ids)
        result = await agent_workflow.run(start_node=RouterNode(), state=state)
        ws = result.state
        elapsed = round(time.time() - start, 3)
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
        return f"{body}\n\n---\n*耗时: {elapsed}s | 模式: 自动路由*"

    agent_name = AgentName(agent_value)
    result = await _run_agent(
        agent_name,
        user_input=message,
        model_alias=model,
        file_ids=ids,
    )
    if result["status"] == "error":
        return f"❌ **错误:** {result['error']}{_format_run_meta(result)}"

    output = result["output"]
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


def _skill_dropdown_update() -> gr.Dropdown:
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
    rows: list[list[str]] = []
    for alias, cfg in MODEL_REGISTRY.items():
        key_ok = "✅" if (not cfg.api_key_env or os.environ.get(cfg.api_key_env)) else "❌"
        rows.append([
            alias,
            cfg.provider,
            cfg.model_id,
            cfg.base_url or "-",
            "是" if cfg.reasoning else "否",
            f"${cfg.cost_per_1m_input:.2f}",
            f"${cfg.cost_per_1m_output:.2f}",
            key_ok,
        ])
    return rows


def refresh_models() -> tuple[list[list[str]], str, str]:
    """
    刷新模型表格、累计成本 Markdown、默认模型信息。

    在 Tab 加载和点击「刷新」时调用。
    """
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
    test_input: str,
    model_alias: str | None,
) -> str:
    """
    Agent 测试 Tab 的运行按钮回调。

    与 Chat 类似，但错误时额外输出完整 JSON 便于调试。
    """
    if not test_input.strip():
        return "请输入测试内容"

    agent_value = AGENT_LABELS.get(agent_label, "qa-assistant")
    if agent_value == "workflow":
        return await _run_chat_agent(test_input, agent_value, model_alias)

    agent_name = AgentName(agent_value)
    result = await _run_agent(
        agent_name,
        user_input=test_input,
        model_alias=model_alias if model_alias else None,
    )
    if result["status"] == "error":
        err_json = json.dumps(result, ensure_ascii=False, indent=2)
        return f"❌ {result['error']}\n\n```json\n{err_json}\n```"

    formatted = _format_agent_output(result["output"], agent_value)
    return f"{formatted}{_format_run_meta(result)}"


# ─── Chat 管理 ───────────────────────────────────

async def chat_submit(
    message: MultimodalInput,
    history: ChatHistory,
    agent_label: str,
    model_alias: str | None,
) -> tuple[ChatHistory, MultimodalInput]:
    """
    发送聊天消息：保存附件、追加 user/assistant 两条记录，并清空输入框。

    Gradio 要求返回 (更新后的 history, 清空的 input)。
    """
    text, file_ids = _save_multimodal_uploads(message)
    if not text and not file_ids:
        return history, EMPTY_MULTIMODAL_INPUT

    agent_value = AGENT_LABELS.get(agent_label, "qa-assistant")
    reply = await _run_chat_agent(text, agent_value, model_alias, file_ids=file_ids)
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
        "session": session_name or "default",
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
            "Chat · Agent · Model · Skills 统一管理界面"
        )

        with gr.Tabs():
            # ── Chat Tab：多轮对话 ──
            with gr.Tab("💬 Chat"):
                with gr.Row():
                    chat_agent = gr.Dropdown(
                        choices=[label for label, _ in AGENT_CHOICES],
                        value=AGENT_CHOICES[0][0],
                        label="Agent 模式",
                    )
                    chat_model = gr.Dropdown(
                        choices=MODEL_CHOICES,
                        value=MODEL_CHOICES[0],
                        label="模型",
                        allow_custom_value=False,
                    )
                    session_name = gr.Textbox(
                        label="会话名称",
                        placeholder="default",
                        scale=1,
                    )
                chatbot = gr.Chatbot(label="对话", height=420)
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
                    inputs=[chat_input, chatbot, chat_agent, chat_model],
                    outputs=[chatbot, chat_input],
                )
                chat_input.submit(
                    chat_submit,
                    inputs=[chat_input, chatbot, chat_agent, chat_model],
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
                test_input = gr.Textbox(
                    label="测试输入",
                    lines=4,
                    placeholder="输入测试内容，例如：查询北京明天天气",
                )
                test_run = gr.Button("运行测试", variant="primary")
                test_output = gr.Markdown(label="测试结果")

                test_run.click(
                    run_agent_test,
                    inputs=[test_agent, test_input, test_model],
                    outputs=[test_output],
                )

            # ── Model Tab：注册表与成本 ──
            with gr.Tab("🧠 Model"):
                gr.Markdown("### 模型注册表")
                model_headers = [
                    "别名", "Provider", "Model ID", "Base URL",
                    "推理", "输入$/1M", "输出$/1M", "API Key",
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
