"""pytest 全局配置文件（conftest.py）。

本文件在**整个测试套件**运行前自动加载，用于：

1. 设置测试专用环境变量（数据库、API Key 等），避免污染真实配置
2. 调用 ``bootstrap_env()`` 初始化应用配置
3. 提供 ``reset_llm_manager`` fixture，保证每个测试用例的 LLM 单例状态干净

什么是 conftest.py？
- pytest 约定：放在 ``tests/`` 下的 ``conftest.py`` 会被自动发现
- 其中定义的 ``@pytest.fixture`` 可被同目录及子目录的测试文件直接使用，无需 import

什么是 fixture？
- pytest 的「测试夹具」：在测试运行前/后准备或清理数据、对象、环境
- ``autouse=True`` 表示该 fixture 会自动应用于每个测试，无需在测试函数参数里声明
"""

import os

import pytest

# ── 测试环境变量 ──────────────────────────────────────────────
# setdefault：仅当环境变量尚未设置时才写入，不覆盖用户已 export 的值
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./data/test.db")

from app.core.config import bootstrap_env

# 根据 APP_ENV 等加载 .env.test 等配置文件
bootstrap_env()

# 单元测试不需要真实 API Key，用占位符即可
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-for-unit-tests")


@pytest.fixture(autouse=True)
def reset_llm_manager():
    """每个测试前后重置 LlmManager 单例。

    LlmManager 在模块内用全局变量 ``_llm_manager`` 缓存实例。
    若不在测试间清空，前一个测试的缓存可能影响后一个测试的结果。

    ``yield`` 把函数分成两段：
    - yield 之前：测试开始前的准备（此处清空单例）
    - yield 之后：测试结束后的清理（再次清空，防止泄漏到后续用例）
    """
    from app.core.llm import _llm_manager  # noqa: F401 — 确保模块已加载
    import app.core.llm as llm_module

    # 测试前：强制下次 get 时重新创建 LlmManager
    llm_module._llm_manager = None
    yield
    # 测试后：同样清空，保持隔离
    llm_module._llm_manager = None
