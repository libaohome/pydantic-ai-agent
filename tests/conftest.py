"""pytest 全局配置文件（conftest.py）。"""

import os

import pytest

# 在导入 app.core.config 之前注入测试用环境变量（无 .env 时也能跑测试）
_TEST_ENV_DEFAULTS: dict[str, str] = {
    "APP_ENV": "test",
    "APP_SECRET_KEY": "test-secret",
    "DEFAULT_MODEL": "deepseek:deepseek-chat",
    "DEEPSEEK_API_KEY": "test-key-for-unit-tests",
    "LONGCAT_API_KEY": "",
    "LONGCAT_BASE_URL": "https://api.longcat.chat/openai",
    "AGNESAI_API_KEY": "",
    "AGNESAI_BASE_URL": "https://apihub.agnes-ai.com/v1",
    "SENSENOVA_API_KEY": "",
    "SENSENOVA_BASE_URL": "https://token.sensenova.cn/v1",
    "COHERE_API_KEY": "",
    "COHERE_BASE_URL": "https://api.cohere.ai/compatibility/v1",
    "CLOUDFLARE_API_KEY": "",
    "CLOUDFLARE_BASE_URL": "https://api.cloudflare.com/client/v4/accounts/test/ai/v1",
    "LOGFIRE_TOKEN": "",
    "DATABASE_URL": "sqlite+aiosqlite:///./data/test.db",
    "MCP_FETCH_URL": "",
}
for _key, _value in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _value)

from app.core.config import bootstrap_env, get_settings

bootstrap_env()
get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_llm_manager():
    """每个测试前后重置 LlmManager 单例。"""
    from app.core.llm import _llm_manager  # noqa: F401
    import app.core.llm as llm_module

    get_settings.cache_clear()
    llm_module._llm_manager = None
    yield
    get_settings.cache_clear()
    llm_module._llm_manager = None
