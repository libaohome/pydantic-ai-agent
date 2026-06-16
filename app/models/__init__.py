"""数据模型包（``app.models``）— Pydantic 契约与 SQLAlchemy ORM。

本包包含两类「模型」，初学者容易混淆，说明如下：

1. **Pydantic 模型**（``schemas.py``）
   - 用于 API 请求/响应校验、Agent 结构化输入输出
   - 在内存中流转，不直接映射数据库表

2. **SQLAlchemy ORM**（``schema.py``）
   - 用于 SQLite 持久化：对话记录、工具执行日志
   - 通过 ``app.core.deps.init_db()`` 自动建表

在项目中的位置::

    app/
    └── models/
        ├── __init__.py   ← 当前文件（包标识）
        ├── schemas.py
        └── schema.py

当前 ``__init__.py`` 未做 re-export；使用时请直接从子模块导入，例如::

    from app.models.schemas import CodeReviewInput
    from app.models.schema import Conversation, Base
"""
