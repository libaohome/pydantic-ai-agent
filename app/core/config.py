"""应用配置中心 — 从环境变量与 .env 文件加载所有运行时参数。

LLM Provider 的 api_key / base_url 与模型列表存于 SQLite（``llm_credential_groups`` / ``llm_models``）；
``.env`` 仅保留应用级配置。
"""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "data"
UPLOAD_DIR = DATA_DIR / "upload"
DOWNLOAD_DIR = DATA_DIR / "download"
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)


class AppSettings(BaseSettings):
    """应用级配置类，字段自动从 .env 文件和环境变量加载。"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    app_name: str
    app_env: str
    app_secret_key: str
    # 默认模型别名（llm_models.alias）；非 Provider 凭证，可继续放 .env 或使用内置默认值
    default_model: str = "deepseek-chat"

    logfire_token: str
    database_url: str
    mcp_fetch_url: str

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()  # type: ignore[call-arg]


def bootstrap_env() -> None:
    """启动引导：加载 .env 文件。"""
    load_dotenv(ENV_FILE)


bootstrap_env()
