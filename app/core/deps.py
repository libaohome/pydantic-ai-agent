"""依赖注入容器 — Agent 运行时依赖与数据库会话管理。

本模块位于 ``app/core/`` 包内，负责两类「依赖」：

1. **基础设施依赖**：异步数据库引擎、SQLAlchemy 会话的创建与获取
2. **业务依赖**：``AgentDeps`` 数据类，注入到 Pydantic AI Agent 的工具函数中

在项目中的位置::

    app/
    └── core/
        ├── deps.py        ← 当前文件
        ├── config.py      ← 读取 database_url 等配置
        └── ...

    app/models/schema.py   ← ORM 表定义（建表时引用 Base）

FastAPI 的 ``Depends(get_session)`` 和 Pydantic AI 的 ``RunContext[AgentDeps]``
都会用到本模块提供的对象。
"""

from __future__ import annotations

# ``@dataclass`` 装饰器：自动生成 ``__init__``、``__repr__`` 等方法，减少样板代码
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

# SQLAlchemy 异步扩展：``AsyncSession`` 是异步会话；``create_async_engine`` 创建异步引擎
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import get_settings, DATA_DIR


# ─── 数据库引擎 ──────────────────────────────────

# 模块级私有变量，用 ``None`` 表示「尚未初始化」（懒加载模式）
_engine = None
_session_factory = None


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    """确保 SQLite 数据库文件的父目录存在。

    SQLite 不会自动创建中间目录；若 ``data/`` 不存在，建库会失败。

    Args:
        database_url: SQLAlchemy 连接字符串，如 ``sqlite+aiosqlite:///path/to/db``。

    Returns:
        None
    """
    if not database_url.startswith("sqlite"):
        return

    # ``split("///", 1)`` 最多分割一次，取出文件路径部分
    db_path_str = database_url.split("///", 1)[-1]
    if not db_path_str or db_path_str == ":memory:":
        return

    db_path = Path(db_path_str)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    # ``parents=True`` 递归创建父目录；``exist_ok=True`` 已存在不报错
    db_path.parent.mkdir(parents=True, exist_ok=True)


async def init_db() -> None:
    """初始化数据库：创建异步引擎、会话工厂，并建表。

    在 ``app/main.py`` 的 ``lifespan`` 启动阶段被 ``await`` 调用。

    Returns:
        None
    """
    # ``global`` 声明要修改模块级变量，而非在函数内创建局部变量
    global _engine, _session_factory
    settings = get_settings()
    _ensure_sqlite_parent_dir(settings.database_url)
    _engine = create_async_engine(settings.database_url, echo=False)
    # ``async_sessionmaker`` 是会话工厂，每次调用 ``()`` 产生新的 AsyncSession
    # ``expire_on_commit=False``：提交后对象属性仍可访问，无需 refresh
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    # 延迟导入避免循环依赖（schema 可能间接引用 deps）
    from app.models.schema import Base
    # ``async with`` 异步上下文管理器：退出时自动 commit/rollback 并关闭连接
    async with _engine.begin() as conn:
        # ``run_sync`` 在异步连接上运行同步函数（SQLAlchemy 建表 API 仍是同步的）
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """异步生成器：为每个请求提供一个数据库会话（FastAPI 依赖注入用法）。

    函数体内有 ``yield``，使其成为**异步生成器**。FastAPI 的 ``Depends(get_session)``
    会在请求开始时执行到 ``yield``，把 ``session`` 注入路由函数；请求结束后
    继续执行 ``yield`` 之后的清理代码（关闭会话）。

    Yields:
        AsyncSession: 当前请求的数据库会话。
    """
    if _session_factory is None:
        await init_db()
    # ``assert`` 告诉类型检查器此处 _session_factory 一定非 None
    assert _session_factory is not None
    async with _session_factory() as session:
        yield session


@asynccontextmanager
async def db_session_scope():
    """为 Agent 运行提供短生命周期的数据库会话（非 FastAPI 请求路径使用）。"""
    if _session_factory is None:
        await init_db()
    assert _session_factory is not None
    async with _session_factory() as session:
        yield session


# ─── Agent 依赖类型 ──────────────────────────────

@dataclass
class AgentDeps:
    """注入到每个 Pydantic AI Agent 的运行时上下文依赖。

    Agent 工具函数通过 ``RunContext[AgentDeps]`` 访问此对象，例如::

        @agent.tool
        async def my_tool(ctx: RunContext[AgentDeps], query: str) -> str:
            tenant = ctx.deps.tenant_id
            ...

    Attributes:
        tenant_id: 租户标识，多租户场景下区分不同客户。
        user_id: 当前用户标识。
        session_id: 用户会话标识，同一用户的多轮对话归属。
        db_session: 可选的数据库会话，用于工具内持久化数据。
        request_id: 请求追踪 ID，便于日志关联。
        file_ids: 本次请求关联的上传文件 ID 列表（对应 data/upload 下文件名）。
        metadata: 任意附加元数据的字典。
    """

    tenant_id: str = "default"
    user_id: str = "anonymous"
    session_id: str = "session01"
    # ``X | None`` 是 Python 3.10+ 的可选类型写法，等价于 ``Optional[X]``
    db_session: AsyncSession | None = None
    request_id: str = ""
    file_ids: list[str] = field(default_factory=list)
    # ``field(default_factory=dict)``：每个实例独立创建新 dict，避免可变默认参数陷阱
    metadata: dict = field(default_factory=dict)
