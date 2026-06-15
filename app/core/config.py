"""Pydantic AI Agent — 应用配置中心"""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# ─── 项目根目录 ──────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# pydantic-ai provider 直接从 os.environ 读取 API Key
_API_KEY_FIELDS = (
    ("DEEPSEEK_API_KEY", "deepseek_api_key"),
    ("OPENAI_API_KEY", "openai_api_key"),
    ("ANTHROPIC_API_KEY", "anthropic_api_key"),
    ("GOOGLE_API_KEY", "google_api_key"),
)


class AppSettings(BaseSettings):
    """应用级配置，自动从 .env / 环境变量加载"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 环境
    app_env: str = "development"
    app_secret_key: str = "change-me-in-production"
    debug: bool = False

    # 默认模型
    default_model: str = "deepseek:deepseek-chat"

    # API Keys（仅供 pydantic-ai 内部使用）
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    deepseek_api_key: str = ""

    # 可观测性
    logfire_token: str = ""

    # 数据库
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR / 'agent.db'}"

    # MCP
    mcp_fetch_url: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()


def bootstrap_env() -> None:
    """加载 .env 并将 API Key 同步到 os.environ，供 pydantic-ai provider 使用。"""
    load_dotenv(ENV_FILE)
    settings = AppSettings()
    for env_var, field_name in _API_KEY_FIELDS:
        if not os.environ.get(env_var):
            value = getattr(settings, field_name, "")
            if value:
                os.environ[env_var] = value


bootstrap_env()
