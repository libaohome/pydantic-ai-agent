"""Pydantic AI Agent 核心包（``app.core``）— 统一对外导出基础设施。

本包聚合了应用运行所需的核心能力，其他模块可通过::

    from app.core import get_settings, get_llm_manager, AgentDeps

一次性导入常用对象，而无需记住具体子模块路径。

在项目中的位置::

    app/
    └── core/
        ├── __init__.py   ← 当前文件（包入口，定义公开 API）
        ├── config.py     ← 配置
        ├── deps.py       ← 依赖注入与数据库
        ├── llm_manager.py  ← LLM 管理
        └── observability.py  ← 可观测性

``__all__`` 列表声明「公开 API」：``from app.core import *`` 时只导出这些名称。
"""

from __future__ import annotations

from app.core.config import get_settings, AppSettings
from app.core.llm_manager import get_llm_manager, LlmManager, ModelAlias
from app.core.deps import AgentDeps, init_db, get_session
from app.core.observability import setup_observability

# 显式列出包对外暴露的符号，便于 IDE 自动补全和 ``import *`` 控制
__all__ = [
    "get_settings",
    "AppSettings",
    "get_llm_manager",
    "LlmManager",
    "ModelAlias",
    "AgentDeps",
    "init_db",
    "get_session",
    "setup_observability",
]
