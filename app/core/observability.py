"""可观测性配置 — Logfire 全链路追踪"""

from __future__ import annotations

from typing import TYPE_CHECKING

import logfire
from app.core.config import get_settings

if TYPE_CHECKING:
    from fastapi import FastAPI

_PLACEHOLDER_TOKENS = frozenset({"", "xxx", "your-token-here", "change-me"})


def _is_logfire_enabled(token: str) -> bool:
    return token.strip().lower() not in _PLACEHOLDER_TOKENS


def setup_observability(app: FastAPI) -> None:
    """初始化 Logfire 可观测性（应用启动时调用一次）"""
    settings = get_settings()

    if _is_logfire_enabled(settings.logfire_token):
        logfire.configure(
            token=settings.logfire_token,
            environment=settings.app_env,
            service_name="pydantic-ai-agent",
        )
        # 自动追踪 FastAPI 请求
        logfire.instrument_fastapi(app)
        # 自动追踪 HTTP 客户端调用
        logfire.instrument_httpx()
        # 自动追踪 Pydantic AI Agent 运行
        logfire.instrument_pydantic_ai()

        print("[Observability] Logfire enabled")
    else:
        # 开发环境：只输出到控制台
        logfire.configure(send_to_logfire=False)
        print("[Observability] Console-only mode (no LOGFIRE_TOKEN)")
