"""可观测性配置 — Logfire 全链路追踪与日志集成。

本模块位于 ``app/core/`` 包内，在应用启动时一次性配置 Logfire，
实现对 FastAPI、HTTP 客户端、Pydantic AI Agent 的自动埋点。

职责概览：
    - 根据 ``LOGFIRE_TOKEN`` 决定启用云端追踪或仅控制台输出
    - 为 FastAPI 应用注册自动 instrumentation（无需手动打日志）

在项目中的位置::

    app/
    └── core/
        ├── observability.py  ← 当前文件
        ├── config.py         ← 读取 logfire_token、app_env
        └── ...

    app/main.py 的 lifespan 中调用 setup_observability(app)
"""

from __future__ import annotations

# ``TYPE_CHECKING`` 为 False 时不执行块内 import，仅用于类型注解，避免运行时循环导入
from typing import TYPE_CHECKING

import logfire
from app.core.config import get_settings

if TYPE_CHECKING:
    from fastapi import FastAPI

# ``frozenset`` 是不可变集合，查找 O(1)，适合存放占位符 token 黑名单
_PLACEHOLDER_TOKENS = frozenset({"", "xxx", "your-token-here", "change-me"})


def _is_logfire_enabled(token: str) -> bool:
    """判断 Logfire token 是否为有效配置（非空且非占位符）。

    Args:
        token: 从配置读取的 logfire_token 字符串。

    Returns:
        bool: token 有效时为 True，应启用云端 Logfire。
    """
    return token.strip().lower() not in _PLACEHOLDER_TOKENS


def setup_observability(app: FastAPI) -> None:
    """初始化 Logfire 可观测性（应用启动时调用一次）。

    根据 token 是否存在，分两种模式：
        - **云端模式**：发送 trace 到 Logfire，并自动 instrument 多个库
        - **控制台模式**：仅本地 logfire 输出，适合开发环境

    Args:
        app: FastAPI 应用实例，用于注册 FastAPI 请求追踪。

    Returns:
        None
    """
    settings = get_settings()

    if _is_logfire_enabled(settings.logfire_token):
        logfire.configure(
            token=settings.logfire_token,
            environment=settings.app_env,
            service_name="pydantic-ai-agent",
        )
        # instrument_* 系列：猴子补丁式注入追踪，自动记录请求/调用链
        logfire.instrument_fastapi(app)
        logfire.instrument_httpx()
        logfire.instrument_pydantic_ai()

        print("[Observability] Logfire enabled")
    else:
        # ``send_to_logfire=False``：不向云端发送，只在本地控制台输出结构化日志
        logfire.configure(send_to_logfire=False)
        print("[Observability] Console-only mode (no LOGFIRE_TOKEN)")
