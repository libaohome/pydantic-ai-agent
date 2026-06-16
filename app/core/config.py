"""应用配置中心 — 从环境变量与 .env 文件加载所有运行时参数。

本模块位于 ``app/core/`` 包内，是项目的**配置单一来源（Single Source of Truth）**。

职责概览：
    - 定义 ``AppSettings`` 配置类（基于 Pydantic Settings）
    - 计算项目路径（``BASE_DIR``、``DATA_DIR`` 等）
    - 提供 ``get_settings()`` 缓存单例，避免重复解析
    - 启动时将 API Key 同步到 ``os.environ``，供 pydantic-ai 底层读取

在项目中的位置::

    app/
    └── core/
        ├── config.py    ← 当前文件
        ├── deps.py      ← 依赖注入（读取本模块配置）
        ├── llm.py       ← LLM 管理（读取 default_model 等）
        └── observability.py  ← 可观测性（读取 logfire_token）
"""

# from __future__ import annotations

import os
from pathlib import Path
# ``lru_cache`` 装饰器：对无参函数结果做 LRU 缓存，同一进程内只创建一次 AppSettings
from functools import lru_cache

from dotenv import load_dotenv
# ``BaseSettings``：Pydantic 的配置基类，自动从环境变量映射字段
from pydantic_settings import BaseSettings, SettingsConfigDict

# ─── 项目根目录 ──────────────────────────────────
# ``Path(__file__)`` 是当前文件路径；``.resolve()`` 转为绝对路径；``.parent`` 向上一级
BASE_DIR = Path(__file__).resolve().parent.parent  # app/
PROJECT_ROOT = BASE_DIR.parent                      # 项目根目录
ENV_FILE = PROJECT_ROOT / ".env"                    # ``/`` 是 Path 的路径拼接运算符
DATA_DIR = PROJECT_ROOT / "data"
UPLOAD_DIR = DATA_DIR / "upload"
# ``mkdir(exist_ok=True)``：目录不存在则创建，已存在不报错
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

# pydantic-ai 的 provider 直接从 os.environ 读取 API Key，字段名必须是大写环境变量名
# 元组列表：每项是 (环境变量名, AppSettings 字段名) 的映射
_API_KEY_FIELDS = (
    ("DEEPSEEK_API_KEY", "deepseek_api_key"),
    ("OPENAI_API_KEY", "openai_api_key"),
    ("ANTHROPIC_API_KEY", "anthropic_api_key"),
    ("GOOGLE_API_KEY", "google_api_key"),
)

class AppSettings(BaseSettings):
    """应用级配置类，字段自动从 .env 文件和环境变量加载。

    继承 ``BaseSettings`` 后，Pydantic 会：
        1. 读取 ``model_config`` 指定的 ``.env`` 文件
        2. 用环境变量覆盖文件中的值（环境变量优先级更高）
        3. 校验类型，类型不匹配会抛出 ValidationError

    字段名使用 snake_case；对应的环境变量通常是大写，如 ``APP_ENV`` → ``app_env``。
    """

    # ``SettingsConfigDict`` 是 Pydantic v2 的配置字典写法（替代旧版 Config 内部类）
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略 .env 中未在类里声明的额外键，避免报错
    )

    # 环境
    app_env: str = "development"
    app_secret_key: str = "change-me-in-production"

    # 默认 LLM 模型，格式为 ``provider:model_id``（pydantic-ai 约定）
    default_model: str = "deepseek:deepseek-chat"

    # API Keys（仅供 pydantic-ai 内部 provider 使用）
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    deepseek_api_key: str = ""

    # 可观测性：Logfire 云端追踪 token
    logfire_token: str = ""

    # 数据库连接 URL；``sqlite+aiosqlite`` 表示异步 SQLite 驱动
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR / 'agent.db'}"

    # MCP（Model Context Protocol）外部服务地址
    mcp_fetch_url: str = ""

    @property
    def is_production(self) -> bool:
        """只读属性：判断当前是否为生产环境。

        ``@property`` 装饰器让方法可以像属性一样访问（``settings.is_production``，
        不需要加括号调用）。

        Returns:
            bool: ``app_env == "production"`` 时为 True。
        """
        return self.app_env == "production"


@lru_cache
def get_settings() -> AppSettings:
    """获取应用配置单例（带 LRU 缓存）。

    ``@lru_cache`` 保证整个进程生命周期内只实例化一次 ``AppSettings``，
    避免重复读取磁盘上的 .env 文件。

    Returns:
        AppSettings: 全局配置对象。
    """
    return AppSettings()


def bootstrap_env() -> None:
    """启动引导：加载 .env 并将 API Key 同步到 ``os.environ``。

    pydantic-ai 的各 provider（OpenAI、Anthropic 等）在运行时直接从
    ``os.environ`` 读取 ``OPENAI_API_KEY`` 等变量，而不是读我们的
    ``AppSettings``。因此需要把 .env 里的值「桥接」到系统环境变量。

    注意：仅当环境变量**尚未设置**时才写入，避免覆盖运维/容器注入的值。

    Returns:
        None
    """
    load_dotenv(ENV_FILE)
    settings = AppSettings()
    # 解包元组：``env_var`` 是环境变量名，``field_name`` 是 AppSettings 字段名
    for env_var, field_name in _API_KEY_FIELDS:
        if env_var in os.environ:
            continue

        value = getattr(settings, field_name, None)
        if value:
            os.environ[env_var] = value

# 模块导入时立即执行，确保后续 import 其他模块前环境变量已就绪
bootstrap_env()
