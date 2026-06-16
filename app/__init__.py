"""Pydantic AI Agent 应用包（``app``）— 项目 Python 代码的根命名空间。

本目录是整个 Web 服务与 Agent 逻辑的**顶层包**。Python 通过包结构组织代码：

- ``app.main``：FastAPI 应用入口（``uvicorn app.main:app``）
- ``app.core``：配置、数据库、LLM、可观测性等基础设施
- ``app.models``：Pydantic 数据契约与 SQLAlchemy ORM
- ``app.api``：REST API 路由
- ``app.agents``：各类 Pydantic AI Agent 实现
- ``app.skills``：可扩展 Skill 包管理
- ``app.ui``：Gradio Web 管理界面

在项目中的位置::

    pydantic-ai-agent/          # 项目根目录（含 pyproject.toml、README）
    └── app/                    # ← 当前包
        ├── __init__.py         # 本文件
        ├── main.py
        ├── core/
        ├── models/
        └── ...

安装或开发模式下，需将项目根目录加入 ``PYTHONPATH``，才能 ``import app``。
通常由 ``uv run``、``pip install -e .`` 或 IDE 自动配置完成。
"""
