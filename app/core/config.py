"""应用配置中心 — 从环境变量与 .env 文件加载所有运行时参数。

所有配置项必须在 ``.env`` 或环境变量中显式提供，代码内不设业务默认值。
"""

# from __future__ import annotations

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

_API_KEY_FIELDS = (
    ("DEEPSEEK_API_KEY", "deepseek_api_key"),
    ("LONGCAT_API_KEY", "longcat_api_key"),
    ("AGNESAI_API_KEY", "agnesai_api_key"),
    ("SENSENOVA_API_KEY", "sensenova_api_key"),
    ("COHERE_API_KEY", "cohere_api_key"),
    ("CLOUDFLARE_API_KEY", "cloudflare_api_key"),
)


class AppSettings(BaseSettings):
    """应用级配置类，字段自动从 .env 文件和环境变量加载。"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str
    app_secret_key: str
    default_model: str

    deepseek_api_key: str
    longcat_api_key: str
    longcat_base_url: str
    agnesai_api_key: str
    agnesai_base_url: str
    sensenova_api_key: str
    sensenova_base_url: str
    cohere_api_key: str
    cohere_base_url: str
    cloudflare_api_key: str
    cloudflare_base_url: str

    logfire_token: str
    database_url: str
    mcp_fetch_url: str

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"
@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
def bootstrap_env() -> None:
    """启动引导：加载 .env 并将 API Key 同步到 ``os.environ``。"""
    load_dotenv(ENV_FILE)
    settings = AppSettings()
    for env_var, field_name in _API_KEY_FIELDS:
        if env_var in os.environ:
            continue
        value = getattr(settings, field_name, None)
        if value:
            os.environ[env_var] = value


bootstrap_env()
