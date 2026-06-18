"""ImageGenAgent — 文生图专用 Agent，调用 images/generations API。"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
from pydantic_ai import Agent

from app.agents.chat_media import supports_image_generation
from app.core.deps import AgentDeps, RuntimeConfigKeys as RC
from app.core.llm_manager import ModelAlias, get_llm_manager
from app.core.uploads import get_download_store, guess_image_extension
from app.models.schemas import ChatMediaArtifact, ChatModelOutput

# 商汤 token.sensenova.cn /images/generations 当前支持的 size（API 返回 400 时会列出合法值）
SENSENOVA_IMAGE_SIZES: frozenset[str] = frozenset({
    "auto",
    "256x256",
    "512x512",
    "1024x1024",
    "1536x1024",
    "1024x1536",
    "1024x1792",
    "1792x1024",
})
DEFAULT_IMAGE_SIZE = "1024x1024"

RUNTIME_CONFIG: dict[str, Any] = {
    RC.IMAGE_GEN: True,
    RC.RESOLVE_DEFAULT_MODEL: True,
}

image_gen_agent = Agent[AgentDeps, str](
    model="deepseek:deepseek-chat",
    output_type=str,
    deps_type=AgentDeps,
    instructions="""你是文生图 Agent，根据文字描述生成图片。

约束：
- 仅处理生图请求，不进行对话或工具调用。
- 使用与用户相同的语言理解描述。
""",
)


def resolve_image_gen_alias(model_alias: str | None) -> ModelAlias:
    """解析生图模型别名；未指定时取注册表中首个 image_generation 模型。"""
    llm = get_llm_manager()
    if model_alias and llm.has_alias(model_alias):
        if not supports_image_generation(model_alias):
            raise ValueError(f"Model alias is not image generation: {model_alias}")
        return model_alias
    for alias in llm.list_aliases():
        if supports_image_generation(alias):
            return alias
    raise RuntimeError("No image generation model configured in registry")


def normalize_image_size(size: str | None) -> str:
    """校验并规范化生图尺寸；非法值回退为默认尺寸。"""
    if size and size in SENSENOVA_IMAGE_SIZES:
        return size
    return DEFAULT_IMAGE_SIZE


def _extract_api_error(resp: httpx.Response) -> str:
    """从 HTTP 错误响应中提取可读信息。"""
    try:
        body = resp.json()
        err = body.get("error", body)
        if isinstance(err, dict):
            message = err.get("message")
            if message:
                param = err.get("param")
                if param:
                    return f"HTTP {resp.status_code}: {message} (param: {param})"
                return f"HTTP {resp.status_code}: {message}"
        return f"HTTP {resp.status_code}: {body}"
    except Exception:
        text = (resp.text or "").strip()
        if text:
            return f"HTTP {resp.status_code}: {text[:500]}"
        return f"HTTP {resp.status_code} for {resp.request.method} {resp.url}"


async def _resolve_generated_image_bytes(
    item: dict[str, Any],
    client: httpx.AsyncClient,
) -> tuple[bytes, str, str | None]:
    """从 images/generations 单条 data 项解析图片字节。

    兼容 OpenAI 风格 ``url`` 与 ``b64_json`` 两种返回；``url`` 亦支持 data URI。
    """
    b64_json = item.get("b64_json")
    if b64_json:
        return base64.b64decode(b64_json), "image/png", None

    url = item.get("url")
    if not url:
        raise ValueError("Image generation response item missing both url and b64_json")

    if url.startswith("data:"):
        header, _, payload = url.partition(",")
        mime = "image/png"
        if ":" in header:
            meta = header.split(":", 1)[1]
            if ";" in meta:
                mime = meta.split(";", 1)[0]
            elif meta:
                mime = meta
        return base64.b64decode(payload), mime, None

    img_resp = await client.get(url)
    img_resp.raise_for_status()
    content_type = img_resp.headers.get("content-type", "image/png").split(";")[0].strip()
    data = img_resp.content
    if content_type in ("", "application/octet-stream"):
        ext = guess_image_extension(content_type, data) or ".png"
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(ext, "image/png")
    return data, content_type, url


def _image_original_name(item: dict[str, Any], index: int, ext: str) -> str:
    """从 API 返回的 url 路径提取原始文件名（如 ``uuid_0.png``）。"""
    url = item.get("url") or ""
    if not url or url.startswith("data:"):
        return f"generated_{index}{ext}"
    basename = unquote(Path(urlparse(url).path).name)
    if not basename:
        return f"generated_{index}{ext}"
    if Path(basename).suffix:
        return basename
    return f"{basename}{ext}"


async def run_image_generation(
    prompt: str,
    model_alias: ModelAlias,
    *,
    size: str | None = None,
) -> dict[str, Any]:
    """调用 images/generations 接口生图。"""
    llm = get_llm_manager()
    cfg = llm.get_config(model_alias)
    if not cfg.credential_group:
        raise ValueError(f"Model {model_alias} has no credential_group configured")
    api_key, base_url = llm.get_credentials(cfg.credential_group)
    if not base_url:
        raise ValueError(
            f"credential group {cfg.credential_group!r} is not configured in llm_credential_groups"
        )
    if not api_key:
        raise ValueError(
            f"credential group {cfg.credential_group!r} has no api_key configured"
        )
    effective_size = normalize_image_size(size)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": cfg.model_id,
        "prompt": prompt.strip() or "生成一张信息图",
        "size": effective_size,
        "n": 1,
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(f"{base_url.rstrip('/')}/images/generations", headers=headers, json=payload)
        if resp.is_error:
            raise ValueError(_extract_api_error(resp))
        data = resp.json()

        items = data.get("data") or []
        if not items:
            raise ValueError("Image generation response missing data array")

        image_bytes, content_type, image_url = await _resolve_generated_image_bytes(items[0], client)

    store = get_download_store()
    ext = guess_image_extension(content_type, image_bytes) or ".png"
    if content_type in ("", "application/octet-stream"):
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(ext, "image/png")
    original_name = _image_original_name(items[0], 0, ext)
    file_id = store.save_from_bytes(image_bytes, original_name, mime_type=content_type)
    path = str(store.get_path(file_id))

    artifact = ChatMediaArtifact(kind="image", path=path, mime_type=content_type, file_id=file_id)
    if image_url:
        text = f"已根据描述生成图片（模型 {model_alias}）。\n\n原图 URL: {image_url}"
    else:
        text = f"已根据描述生成图片（模型 {model_alias}）。"
    return ChatModelOutput(text=text, artifacts=[artifact]).model_dump()
