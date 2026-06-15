"""pytest 全局配置 — fixtures 与共享设置"""

import os

import pytest

# 确保测试环境使用 .env.test 或空环境
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./data/test.db")

from app.core.config import bootstrap_env

bootstrap_env()
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-for-unit-tests")


@pytest.fixture(autouse=True)
def reset_llm_manager():
    """每个测试前重置 LlmManager 单例"""
    from app.core.llm import _llm_manager
    import app.core.llm as llm_module
    llm_module._llm_manager = None
    yield
    llm_module._llm_manager = None
