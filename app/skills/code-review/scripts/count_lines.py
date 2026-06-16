#!/usr/bin/env python3
"""
代码行数统计脚本 — 供 code-review Skill 通过 run_skill_script 调用。

功能：读取单个文本文件，统计总行数、代码行、空行和注释行（简单启发式）。

命令行用法::

        python count_lines.py <file_path>

标准输出为 JSON，便于 Agent 或 Shell 解析。

面向小白：
- shebang ``#!/usr/bin/env python3`` 表示可直接 ./count_lines.py 执行（需 chmod +x）
- Path 处理路径；read_text 读文件；splitlines 按行拆分
"""

import sys
from pathlib import Path


def count_lines(file_path: str) -> dict:
    """
    统计指定文件的行数信息。

    参数:
            file_path: 文件路径字符串

    返回:
            成功时含 total_lines、code_lines、blank_lines、comment_lines；
            文件不存在时含 error 字段
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    content = path.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()

    total = len(lines)
    # 空行：去掉首尾空白后长度为 0
    blank = sum(1 for line in lines if not line.strip())
    code = total - blank
    # 简单注释检测：行首（去空白后）以 # // /* 开头
    comments = sum(
        1 for line in lines
        if line.strip().startswith("#")
        or line.strip().startswith("//")
        or line.strip().startswith("/*")
    )

    return {
        "file": file_path,
        "total_lines": total,
        "code_lines": code,
        "blank_lines": blank,
        "comment_lines": comments,
    }


if __name__ == "__main__":
    # CLI 入口：第一个参数为文件路径
    if len(sys.argv) < 2:
        print("Usage: python count_lines.py <file_path>")
        sys.exit(1)

    import json
    result = count_lines(sys.argv[1])
    print(json.dumps(result, indent=2))
