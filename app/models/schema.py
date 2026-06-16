"""数据库 ORM 模型 — SQLAlchemy 表定义与持久化结构。

本模块位于 ``app/models/`` 包内，定义**数据库表结构**（与 Pydantic schemas 无关）。

与 ``schemas.py`` 的区别：
    - ``schema.py``（本文件）：映射到 SQLite 表，存储对话记录、工具执行日志
    - ``schemas.py``：内存中的请求/响应对象，不直接对应数据库行

职责概览：
    - ``Base``：所有 ORM 类的声明式基类
    - ``Conversation``：Agent 对话与 token 成本记录
    - ``ToolExecutionLog``：Agent 工具调用的审计日志

在项目中的位置::

    app/
    └── models/
        ├── schema.py    ← 当前文件（SQLAlchemy ORM）
        ├── schemas.py   ← Pydantic 模型
        └── __init__.py

    app/core/deps.py 的 init_db() 会调用 Base.metadata.create_all 建表
"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import String, Text, DateTime, Integer, Float, JSON
# SQLAlchemy 2.0 声明式风格：DeclarativeBase + Mapped 类型注解
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型类的元数据基类。

    子类定义的表会注册到 ``Base.metadata``，供 ``create_all`` 批量建表。
    """

    pass


class Conversation(Base):
    """对话记录表 — 持久化每次 Agent 调用的输入、输出与成本。

    对应数据库表名 ``conversations``（由 ``__tablename__`` 指定）。

    Attributes:
        id: 对话唯一 ID，主键。
        tenant_id: 租户 ID，带索引便于按租户查询。
        user_id: 用户 ID，带索引。
        agent_name: 使用的 Agent 名称。
        model_alias: 使用的模型别名。
        input_text: 用户输入文本。
        output_text: Agent 文本输出，可为空（进行中或失败）。
        output_json: 结构化 JSON 输出，可为空。
        input_tokens / output_tokens: token 用量统计。
        cost_usd: 本次调用美元成本。
        tool_calls: 工具调用详情 JSON，可为空。
        status: 状态，如 pending、completed、failed。
        error_message: 失败时的错误信息。
        created_at / finished_at: 创建与完成时间。
    """

    __tablename__ = "conversations"

    # ``Mapped[str]`` 是类型注解，告诉 SQLAlchemy 列的 Python 类型
    # ``mapped_column(...)`` 定义列约束：主键、索引、可空、默认值等
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_name: Mapped[str] = mapped_column(String(64))
    model_alias: Mapped[str] = mapped_column(String(64))
    input_text: Mapped[str] = mapped_column(Text)
    output_text: Mapped[str] = mapped_column(Text, nullable=True)
    output_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tool_calls: Mapped[dict] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    # ``default=datetime.utcnow`` 注意：传入函数引用，而非 datetime.utcnow() 的调用结果
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class ToolExecutionLog(Base):
    """工具执行日志表 — 记录 Agent 每次工具调用的参数与结果摘要。

    对应数据库表名 ``tool_execution_logs``。主键为自增整数。

    Attributes:
        id: 自增主键。
        conversation_id: 关联的对话 ID，带索引。
        tool_name: 工具名称。
        tool_args: 调用参数字典（JSON 列）。
        result_preview: 结果预览文本，可为空。
        duration_ms: 执行耗时（毫秒），可为空。
        success: 是否执行成功，默认 True。
        created_at: 记录创建时间。
    """

    __tablename__ = "tool_execution_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True)
    tool_name: Mapped[str] = mapped_column(String(128))
    tool_args: Mapped[dict] = mapped_column(JSON)
    result_preview: Mapped[str] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
