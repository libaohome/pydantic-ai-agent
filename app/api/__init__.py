"""API 包初始化 — HTTP 接口层的入口包。

本目录存放 FastAPI 相关的路由、中间件等代码。
``app.api.routes`` 模块中定义的 ``router`` 会在 ``app.main`` 里被挂载到 FastAPI 应用上。

包结构说明：
- ``routes.py``：Agent 相关的 REST API 端点
- 未来可在此包下新增其他路由模块（如健康检查、管理后台等）
"""
from __future__ import annotations

