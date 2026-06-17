"""Agent 输入附件处理 — 解析 file_id 并注入 prompt。

提供统一的 ``prepare_agent_input`` 入口：预读附件内容拼到 user_input 后，
各 Agent 仅在需要时注册专属钩子（如 code_reviewer 的无代码提示）。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.core.uploads import UploadStore, get_upload_store

if TYPE_CHECKING:
    from app.agents.registry import AgentName

_TEXT_SUFFIXES = {
    ".txt", ".md", ".json", ".csv", ".py", ".java", ".kt", ".go",
    ".js", ".ts", ".tsx", ".jsx", ".xml", ".yaml", ".yml", ".sql",
    ".html", ".css", ".sh", ".rb", ".rs",
}


def format_file_ids_hint(file_ids: list[str], store: UploadStore | None = None) -> str:
    """将 file_id 列表格式化为可注入 prompt 的附件说明。"""
    if not file_ids:
        return ""

    upload_store = store or get_upload_store()
    lines = [
        "[系统提示] 用户附带了以下上传文件（file_id 可用于读取）：",
    ]
    for file_id in file_ids:
        try:
            meta = upload_store.get_metadata(file_id)
            lines.append(f"- file_id: `{file_id}` | 原始名: {meta.original_name} | 大小: {meta.size} B")
        except FileNotFoundError:
            lines.append(f"- file_id: `{file_id}` | （文件不存在或已删除）")
    lines.append("可通过 read_uploaded_file 工具或 resolve_upload_path 读取文件内容。")
    return "\n".join(lines)


def enrich_user_input_with_files(user_input: str, file_ids: list[str] | None) -> str:
    """在用户文本后附加附件说明（仅元信息，不预读内容）。"""
    if not file_ids:
        return user_input
    hint = format_file_ids_hint(file_ids)
    text = user_input.strip()
    if not text:
        return hint
    return f"{text}\n\n{hint}"


def _format_file_content_block(file_id: str, content: str) -> str:
    """将单个附件格式化为 markdown 块。"""
    return f"### 附件 `{file_id}`\n\n{content}"


def inject_file_contents(user_input: str, file_ids: list[str] | None) -> str:
    """预读附件文本，以 markdown 块拼到 user_input 后。"""
    if not file_ids:
        return user_input

    text = user_input.strip()
    blocks = [text] if text else []
    for file_id, content in read_uploaded_files(file_ids).items():
        blocks.append(_format_file_content_block(file_id, content))
    return "\n\n".join(blocks)


def prepare_agent_input(
    agent_name: AgentName,
    user_input: str,
    file_ids: list[str] | None = None,
) -> str:
    """按 Agent 类型预处理用户输入：注入附件内容，并应用专属钩子。"""
    from app.agents.registry import AgentName

    text = inject_file_contents(user_input, file_ids)
    if agent_name == AgentName.code_reviewer:
        from app.agents.code_reviewer import apply_review_no_code_hint

        return apply_review_no_code_hint(text, has_attachments=bool(file_ids))
    return text


def resolve_upload_path(file_id: str, store: UploadStore | None = None) -> Path:
    """解析 file_id 为磁盘绝对路径。"""
    return (store or get_upload_store()).get_path(file_id)


def read_uploaded_file(file_id: str, store: UploadStore | None = None) -> str:
    """按 file_id 读取上传文件；文本文件返回内容，二进制返回路径与元信息。"""
    upload_store = store or get_upload_store()
    path = upload_store.get_path(file_id)
    meta = upload_store.get_metadata(file_id)

    if path.suffix.lower() in _TEXT_SUFFIXES:
        content = upload_store.read_text(file_id)
        return (
            f"file_id: {file_id}\n"
            f"original_name: {meta.original_name}\n"
            f"path: {path}\n\n"
            f"{content}"
        )

    return (
        f"file_id: {file_id}\n"
        f"original_name: {meta.original_name}\n"
        f"path: {path}\n"
        f"size: {meta.size} B\n"
        f"（二进制文件，请使用路径或专用工具处理）"
    )


def read_uploaded_files(file_ids: list[str] | None) -> dict[str, str]:
    """批量读取上传文件，返回 file_id → 内容/描述 映射。"""
    if not file_ids:
        return {}
    result: dict[str, str] = {}
    for file_id in file_ids:
        try:
            result[file_id] = read_uploaded_file(file_id)
        except (FileNotFoundError, ValueError) as e:
            result[file_id] = f"Error: {e}"
    return result
