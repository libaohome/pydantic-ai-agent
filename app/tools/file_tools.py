"""工具包 — 通用工具函数"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

from pydantic_ai import RunContext

from app.core.deps import AgentDeps


# ─── 文件操作工具 ──────────────────────────────

async def read_file(path: str, *, ctx: RunContext[AgentDeps] | None = None) -> str:
    """读取文件内容"""
    p = Path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    if p.is_dir():
        return f"Error: '{path}' is a directory, not a file. Use list_directory instead."
    if not p.is_file():
        return f"Error: '{path}' is not a readable file."
    # 安全检查：确保不会越界读取
    if ctx and ctx.deps.metadata.get("sandbox_root"):
        sandbox = Path(ctx.deps.metadata["sandbox_root"])
        if not p.resolve().is_relative_to(sandbox.resolve()):
            return f"Error: access denied — {path} is outside sandbox"
    try:
        return p.read_text(encoding="utf-8")
    except OSError as e:
        return f"Error reading file '{path}': {e}"


async def write_file(path: str, content: str, *, ctx: RunContext[AgentDeps] | None = None) -> str:
    """写入文件"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Successfully wrote {len(content)} chars to {path}"


async def list_directory(path: str = ".", pattern: str = "*") -> str:
    """列出目录内容"""
    p = Path(path)
    if not p.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")
    entries = sorted(p.glob(pattern))
    result = []
    for entry in entries:
        kind = "DIR " if entry.is_dir() else "FILE"
        size = entry.stat().st_size if entry.is_file() else 0
        result.append(f"{kind} {entry.name:40s} {size:>10,} bytes")
    return "\n".join(result) or "Empty directory"


# ─── Shell 执行工具 ────────────────────────────

ALLOWED_COMMANDS = {
    "git", "python3", "python", "pip", "npm", "node",
    "ls", "cat", "head", "tail", "wc", "grep", "find",
    "echo", "pwd", "date", "curl", "jq",
}

BLOCKED_PATTERNS = ["rm -rf", "sudo", "mkfs", "dd if=", "> /dev/", "chmod 777"]


async def run_shell(command: str, timeout: int = 30, *, ctx: RunContext[AgentDeps] | None = None) -> str:
    """安全执行 Shell 命令（白名单 + 黑名单双检）"""
    # 黑名单检查
    cmd_lower = command.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            raise PermissionError(f"Blocked command pattern: {pattern}")

    # 白名单检查
    base_cmd = command.strip().split()[0] if command.strip() else ""
    if base_cmd not in ALLOWED_COMMANDS:
        raise PermissionError(
            f"Command '{base_cmd}' not in allowlist. "
            f"Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}"
        )

    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    output = result.stdout
    if result.returncode != 0:
        output += f"\n[STDERR] {result.stderr}\n[EXIT CODE] {result.returncode}"

    return output[:10_000]  # 截断防止超长输出


# ─── Web 请求工具 ──────────────────────────────

async def fetch_url(url: str, max_chars: int = 5000) -> str:
    """获取 URL 内容（纯文本）"""
    import httpx
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.text[:max_chars]


# ─── JSON / 数据工具 ────────────────────────────

async def parse_json(text: str) -> str:
    """解析和格式化 JSON"""
    try:
        data = json.loads(text)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"


async def current_datetime() -> str:
    """获取当前日期时间"""
    return datetime.now().isoformat()
