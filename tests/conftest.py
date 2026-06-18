"""pytest 全局配置文件（conftest.py）。"""

from __future__ import annotations

import asyncio
import os

import pytest

# 在导入 app.core.config 之前注入测试用环境变量（无 .env 时也能跑测试）
_TEST_ENV_DEFAULTS: dict[str, str] = {
    "APP_ENV": "test",
    "APP_SECRET_KEY": "test-secret",
    "DEFAULT_MODEL": "deepseek-chat",
    "DEEPSEEK_API_KEY": "test-key-for-unit-tests",
    "LOGFIRE_TOKEN": "",
    "DATABASE_URL": "sqlite+aiosqlite:///./data/test.db",
    "MCP_FETCH_URL": "",
}
for _key, _value in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _value)

from app.core.config import bootstrap_env, get_settings

bootstrap_env()
get_settings.cache_clear()


async def _init_test_llm_registry() -> None:
    import app.core.deps as deps_module
    import app.core.llm_manager as llm_module
    from app.core.deps import db_session_scope, init_db
    from app.core.llm_manager import reload_llm_registry
    from tests.fixtures.llm_registry_fixture import ensure_test_llm_registry

    deps_module._engine = None
    deps_module._session_factory = None
    llm_module._llm_manager = None

    await init_db()
    async with db_session_scope() as session:
        if await ensure_test_llm_registry(session):
            await session.commit()
            await reload_llm_registry()


@pytest.fixture(autouse=True)
def reset_llm_manager():
    """每个测试前后重置 LlmManager 并从测试库加载注册表。"""
    get_settings.cache_clear()
    asyncio.run(_init_test_llm_registry())
    yield
    get_settings.cache_clear()
    import app.core.llm_manager as llm_module

    llm_module._llm_manager = None
