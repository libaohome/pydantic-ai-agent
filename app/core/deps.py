"""依赖注入容器 — Agent 运行时依赖"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import get_settings, DATA_DIR


# ─── 数据库引擎 ──────────────────────────────────

_engine = None
_session_factory = None


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    """确保 SQLite 数据库文件的父目录存在。"""
    if not database_url.startswith("sqlite"):
        return

    db_path_str = database_url.split("///", 1)[-1]
    if not db_path_str or db_path_str == ":memory:":
        return

    db_path = Path(db_path_str)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)


async def init_db() -> None:
    """初始化数据库（应用启动时调用）"""
    global _engine, _session_factory
    settings = get_settings()
    _ensure_sqlite_parent_dir(settings.database_url)
    _engine = create_async_engine(settings.database_url, echo=False)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    # 建表
    from app.models.schema import Base
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """获取数据库会话"""
    if _session_factory is None:
        await init_db()
    assert _session_factory is not None
    async with _session_factory() as session:
        yield session


# ─── Agent 依赖类型 ──────────────────────────────

@dataclass
class AgentDeps:
    """注入到每个 Agent 的运行时依赖

    通过 RunContext[AgentDeps] 在工具函数中访问
    """

    tenant_id: str = "default"
    user_id: str = "anonymous"
    db_session: AsyncSession | None = None
    request_id: str = ""
    metadata: dict = field(default_factory=dict)
