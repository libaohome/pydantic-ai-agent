"""
工具包统一导出入口（`app.tools` 包）。

本文件把分散在 file_tools、db_tools、kb_tools 中的函数集中导出，
方便其他模块使用 `from app.tools import read_file, execute_sql, ...` 一次性导入。

`__all__` 列表定义了「公开 API」—— 只有列在其中的名字会被 `from app.tools import *` 导入。
"""

from app.tools.file_tools import (
    read_file,
    write_file,
    list_directory,
    run_shell,
    fetch_url,
    parse_json,
    current_datetime,
)
from app.tools.db_tools import execute_sql, list_tables, describe_table
from app.tools.kb_tools import search_knowledge_base, search_web

# 对外公开的符号列表（IDE 自动补全和 import * 会参考它）
__all__ = [
    "read_file", "write_file", "list_directory",
    "run_shell", "fetch_url", "parse_json", "current_datetime",
    "execute_sql", "list_tables", "describe_table",
    "search_knowledge_base", "search_web",
]
