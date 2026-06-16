"""
通用文件与系统工具模块。

本模块为 AI Agent 提供一组「可被调用的工具函数」，涵盖：
- 文件读写与目录浏览
- 受控的 Shell 命令执行（白名单 + 黑名单）
- HTTP 网页抓取
- JSON 解析与当前时间查询

这些函数通常通过 pydantic-ai 的 Tool 机制注册给 Agent 使用。
所有涉及文件路径的操作都支持可选的沙箱（sandbox）限制，防止越权访问。

面向小白说明：
- `async def` 表示异步函数，Agent 框架会在事件循环中 await 它
- `RunContext[AgentDeps]` 是 pydantic-ai 传入的「运行上下文」，可读取依赖注入的数据
- `Path` 是 Python 标准库 pathlib 的路径对象，比字符串拼接更安全
"""

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
    """
    读取指定路径的文本文件内容。

    参数:
            path: 文件路径（相对或绝对路径均可）
            ctx: 可选的运行上下文；若提供且配置了 sandbox_root，则禁止读取沙箱外文件

    返回:
            文件文本内容；若出错则返回以 "Error:" 开头的错误信息字符串
    """
    p = Path(path)
    # 依次检查：文件是否存在、是否为目录、是否为普通文件
    if not p.exists():
        return f"Error: file not found: {path}"
    if p.is_dir():
        return f"Error: '{path}' is a directory, not a file. Use list_directory instead."
    if not p.is_file():
        return f"Error: '{path}' is not a readable file."
    # 安全检查：若配置了沙箱根目录，则 resolve() 后必须在沙箱内
    if ctx and ctx.deps.metadata.get("sandbox_root"):
        sandbox = Path(ctx.deps.metadata["sandbox_root"])
        if not p.resolve().is_relative_to(sandbox.resolve()):
            return f"Error: access denied — {path} is outside sandbox"
    try:
        return p.read_text(encoding="utf-8")
    except OSError as e:
        return f"Error reading file '{path}': {e}"


async def write_file(path: str, content: str, *, ctx: RunContext[AgentDeps] | None = None) -> str:
    """
    将文本内容写入指定文件。

    若父目录不存在会自动创建（mkdir parents=True）。
    注意：当前实现未做沙箱校验，生产环境建议与 read_file 一样增加路径限制。

    参数:
            path: 目标文件路径
            content: 要写入的字符串内容
            ctx: 预留的运行上下文（暂未使用）

    返回:
            成功时返回写入字符数的确认信息
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)  # 确保父目录存在
    p.write_text(content, encoding="utf-8")
    return f"Successfully wrote {len(content)} chars to {path}"


async def list_directory(path: str = ".", pattern: str = "*") -> str:
    """
    列出目录下的文件和子目录。

    参数:
            path: 要浏览的目录路径，默认为当前目录 "."
            pattern: glob 通配符，例如 "*.py" 只列出 Python 文件

    返回:
            格式化的多行文本，每行包含类型（DIR/FILE）、名称和大小

    异常:
            NotADirectoryError: 当 path 不是目录时抛出
    """
    p = Path(path)
    if not p.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")
    entries = sorted(p.glob(pattern))  # glob 按模式匹配并排序
    result = []
    for entry in entries:
        kind = "DIR " if entry.is_dir() else "FILE"
        size = entry.stat().st_size if entry.is_file() else 0
        result.append(f"{kind} {entry.name:40s} {size:>10,} bytes")
    return "\n".join(result) or "Empty directory"


# ─── Shell 执行工具 ────────────────────────────

# 允许执行的基础命令白名单（仅匹配命令的第一个单词）
ALLOWED_COMMANDS = {
    "git", "python3", "python", "pip", "npm", "node",
    "ls", "cat", "head", "tail", "wc", "grep", "find",
    "echo", "pwd", "date", "curl", "jq",
}

# 危险命令片段黑名单（子串匹配，不区分大小写）
BLOCKED_PATTERNS = ["rm -rf", "sudo", "mkfs", "dd if=", "> /dev/", "chmod 777"]


async def run_shell(command: str, timeout: int = 30, *, ctx: RunContext[AgentDeps] | None = None) -> str:
    """
    在受控条件下执行 Shell 命令。

    安全策略：
    1. 黑名单：若命令中包含危险片段则直接拒绝
    2. 白名单：命令的第一个词必须在 ALLOWED_COMMANDS 中
    3. 超时：默认 30 秒，防止命令卡死
    4. 输出截断：最多返回 10000 字符，防止刷屏

    参数:
            command: 完整 shell 命令字符串
            timeout: 超时秒数
            ctx: 预留上下文（可扩展为限制工作目录等）

    返回:
            标准输出；非零退出码时会附加 STDERR 和退出码信息
    """
    # 黑名单检查（转小写后做子串匹配）
    cmd_lower = command.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            return f"Error: blocked command pattern: {pattern}"

    # 白名单检查：取命令第一个 token 作为基础命令名
    base_cmd = command.strip().split()[0] if command.strip() else ""
    if base_cmd not in ALLOWED_COMMANDS:
        return (
            f"Error: command '{base_cmd}' not in allowlist. "
            f"Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}"
        )

    try:
        result = subprocess.run(
            command,
            shell=True,           # 通过 shell 解析管道、重定向等
            capture_output=True,  # 捕获 stdout/stderr
            text=True,            # 以文本而非字节返回
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    except OSError as e:
        return f"Error executing command: {e}"

    output = result.stdout
    if result.returncode != 0:
        output += f"\n[STDERR] {result.stderr}\n[EXIT CODE] {result.returncode}"

    return output[:10_000]  # 截断防止超长输出淹没上下文


# ─── Web 请求工具 ──────────────────────────────

async def fetch_url(url: str, max_chars: int = 5000) -> str:
    """
    通过 HTTP GET 获取网页的纯文本内容。

    参数:
            url: 目标网址
            max_chars: 最多返回的字符数，默认 5000

    返回:
            响应体文本的前 max_chars 个字符

    依赖:
            httpx（在函数内延迟导入，避免未使用时加载）
    """
    import httpx
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, follow_redirects=True)  # 自动跟随重定向
        resp.raise_for_status()  # 4xx/5xx 会抛异常
        return resp.text[:max_chars]


# ─── JSON / 数据工具 ────────────────────────────

async def parse_json(text: str) -> str:
    """
    解析 JSON 字符串并格式化为易读的缩进形式。

    参数:
            text: 原始 JSON 文本

    返回:
            格式化后的 JSON；解析失败时返回错误说明
    """
    try:
        data = json.loads(text)
        return json.dumps(data, indent=2, ensure_ascii=False)  # 保留中文不转义
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"


async def current_datetime() -> str:
    """
    获取当前本地日期时间的 ISO 8601 格式字符串。

    示例返回值: "2026-06-16T14:30:00.123456"
    """
    return datetime.now().isoformat()
