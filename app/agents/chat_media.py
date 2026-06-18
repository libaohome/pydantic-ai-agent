"""ChatModelAgent 多模态输入构建与生成物序列化。"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, TypeGuard

from pydantic_ai.messages import BinaryContent, FilePart, ModelMessage, UserContent

from app.core.llm_manager import ModelAlias, get_llm_manager
from app.core.uploads import get_download_store, get_upload_store, guess_image_extension
from app.models.schemas import ChatMediaArtifact, ChatModelOutput

_TEXT_SUFFIXES = {
    ".txt", ".md", ".json", ".csv", ".py", ".java", ".kt", ".go",
    ".js", ".ts", ".tsx", ".jsx", ".xml", ".yaml", ".yml", ".sql",
    ".html", ".css", ".sh", ".rb", ".rs",
}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".heic", ".heif"}
_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".mpeg", ".mpg"}
_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}


def resolve_chat_model_alias(model_alias: str | None) -> ModelAlias:
    llm = get_llm_manager()
    if model_alias and llm.has_alias(model_alias):
        return model_alias
    return llm.default_alias()


def supports_image_generation(alias: ModelAlias) -> bool:
    return get_llm_manager().get_config(alias).image_generation


def supports_multimodal_input(alias: ModelAlias) -> bool:
    return get_llm_manager().get_config(alias).multimodal


def resolve_agent_for_model_alias(model_alias: str | None) -> "AgentName":
    """按模型能力选择 chat-model 或 image-gen Agent。"""
    from app.agents.registry import AgentName

    llm = get_llm_manager()
    if model_alias and llm.has_alias(model_alias):
        if supports_image_generation(model_alias):
            return AgentName.image_gen
        return AgentName.chat_model
    return AgentName.chat_model


def get_chat_builtin_tools(model_alias: str | None) -> list[Any]:
    return []


def _guess_media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _read_text_attachment(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def build_chat_user_prompt(
    user_input: str,
    file_ids: list[str] | None = None,
    *,
    model_alias: str | None = None,
) -> str | list[UserContent]:
    """将文本与附件组装为 pydantic-ai 可接受的用户输入。"""
    alias = resolve_chat_model_alias(model_alias)

    if not file_ids:
        return user_input.strip() or "你好"

    store = get_upload_store()
    multimodal = supports_multimodal_input(alias)
    parts: list[UserContent] = []

    if user_input.strip():
        parts.append(user_input.strip())

    for file_id in file_ids:
        try:
            path = store.get_path(file_id)
            meta = store.get_metadata(file_id)
        except (FileNotFoundError, ValueError) as e:
            parts.append(f"[附件 `{file_id}` 无法读取: {e}]")
            continue

        suffix = path.suffix.lower()
        if suffix in _TEXT_SUFFIXES:
            parts.append(
                f"### 文本附件 `{meta.original_name}`\n\n{_read_text_attachment(path)}"
            )
        elif suffix in _IMAGE_SUFFIXES and multimodal:
            parts.append(
                BinaryContent(
                    data=path.read_bytes(),
                    media_type=_guess_media_type(path),
                )
            )
        elif suffix in _IMAGE_SUFFIXES | _VIDEO_SUFFIXES | _AUDIO_SUFFIXES:
            parts.append(
                f"[媒体附件 `{meta.original_name}`：当前模型 `{alias}` 不支持该媒体类型，"
                f"请换用支持多模态的模型（如 sensenova-6.7-flash-lite、cohere-command-a-plus）或上传文本文件。]"
            )
        else:
            parts.append(
                f"[二进制附件 `{meta.original_name}` | file_id: `{file_id}` | 路径: `{path}`]"
            )

    if not parts:
        return "请处理以上附件。"
    if _all_str_parts(parts):
        return "\n\n".join(parts)
    if len(parts) == 1 and isinstance(parts[0], str):
        return parts[0]
    return parts

def _all_str_parts(parts: list[UserContent]) -> TypeGuard[list[str]]:
    return all(isinstance(p, str) for p in parts)


def serialize_chat_model_result(result: Any) -> dict[str, Any]:
    """从 Agent 运行结果提取文本与模型生成的媒体文件。"""
    from pydantic_ai import BinaryContent

    text = str(result.output or "").strip()
    artifacts: list[ChatMediaArtifact] = []
    store = get_download_store()

    messages: list[ModelMessage] = []
    if hasattr(result, "new_messages"):
        messages = list(result.new_messages() or [])

    for message in messages:
        for part in message.parts:
            if not isinstance(part, FilePart):
                continue
            content = part.content
            if not isinstance(content, BinaryContent):
                continue
            mime = content.media_type or "application/octet-stream"
            ext = guess_image_extension(mime, content.data)
            if ext:
                kind = "image"
                if mime == "application/octet-stream":
                    mime = {
                        ".png": "image/png",
                        ".jpg": "image/jpeg",
                        ".gif": "image/gif",
                        ".webp": "image/webp",
                    }.get(ext, "image/png")
            else:
                kind = "file"
                ext = mimetypes.guess_extension(mime) or ".bin"
            file_id = store.save_from_bytes(content.data, f"generated{ext}", mime_type=mime)
            path = str(store.get_path(file_id))
            artifacts.append(
                ChatMediaArtifact(kind=kind, path=path, mime_type=mime, file_id=file_id)
            )

    output = ChatModelOutput(text=text, artifacts=artifacts)
    return output.model_dump()


def format_chat_model_output_markdown(output: Any) -> str:
    """将 ChatModelOutput 格式化为 Gradio Markdown。"""
    if isinstance(output, dict):
        data = output
    elif hasattr(output, "model_dump"):
        data = output.model_dump()
    else:
        return str(output)

    lines: list[str] = []
    text = data.get("text", "")
    if text:
        lines.append(text)

    for art in data.get("artifacts") or []:
        kind = art.get("kind", "file")
        path = art.get("path", "")
        mime = art.get("mime_type", "")
        if kind == "image" and path and Path(path).is_file():
            raw = Path(path).read_bytes()
            b64 = base64.standard_b64encode(raw).decode("ascii")
            lines.append(f"\n![生成图片](data:{mime};base64,{b64})")
        elif path:
            lines.append(f"\n**生成{kind}:** `{path}`")

    return "\n".join(lines) if lines else "（模型未返回文本）"
