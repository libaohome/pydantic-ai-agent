#!/usr/bin/env python3
"""代码统计脚本 — 被 code-review skill 的 run_skill_script 调用"""

import sys
from pathlib import Path


def count_lines(file_path: str) -> dict:
    """统计文件的行数信息"""
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    content = path.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()

    total = len(lines)
    blank = sum(1 for line in lines if not line.strip())
    code = total - blank
    # 简单的注释检测
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
    if len(sys.argv) < 2:
        print("Usage: python count_lines.py <file_path>")
        sys.exit(1)

    import json
    result = count_lines(sys.argv[1])
    print(json.dumps(result, indent=2))
