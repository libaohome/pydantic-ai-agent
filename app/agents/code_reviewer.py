"""代码审查 Agent — 结构化代码审查，返回类型安全的审查报告"""

from __future__ import annotations

import logfire

from pydantic_ai import Agent, RunContext

from app.core.deps import AgentDeps
from app.core.llm import get_llm_manager, ModelAlias
from app.models.schemas import CodeReviewOutput


# ─── Agent 定义 ──────────────────────────────────

code_review_agent = Agent[AgentDeps, CodeReviewOutput](
    model=get_llm_manager().resolve_model_string("deepseek-chat"),
    output_type=CodeReviewOutput,
    deps_type=AgentDeps,
    instructions="""你是一名资深代码审查工程师。你的任务：

1. 仔细审查用户提交的代码
2. 从以下维度评估：
   - 代码正确性：逻辑错误、边界条件、异常处理
   - 安全性：注入攻击、数据泄露、权限问题
   - 性能：时间/空间复杂度、N+1 查询、内存泄漏
   - 可维护性：命名规范、函数长度、圈复杂度
   - 最佳实践：设计模式、SOLID 原则、DRY

3. 每个问题必须给出：
   - 精确的行号
   - 严重程度（critical / warning / info）
   - 清晰的问题描述
   - 可操作的修复建议

4. 给出总体质量评分（0-100）和是否通过的判断

注意：
- 使用 read_file 工具读取源代码文件
- 使用 run_shell 工具运行静态分析（如 ruff, mypy）
- 审查要严格但不吹毛求疵，info 级别留给风格偏好
""",
)


# ─── 注册工具 ──────────────────────────────────

@code_review_agent.tool
async def read_source_file(ctx: RunContext[AgentDeps], path: str) -> str:
    """读取源代码文件"""
    from app.tools.file_tools import read_file
    return await read_file(path, ctx=ctx)


@code_review_agent.tool
async def run_linter(ctx: RunContext[AgentDeps], command: str) -> str:
    """运行代码检查工具（ruff, mypy, eslint 等）"""
    from app.tools.file_tools import run_shell
    with logfire.span("run_linter", command=command):
        return await run_shell(command, ctx=ctx)


@code_review_agent.tool
async def check_test_coverage(ctx: RunContext[AgentDeps], path: str) -> str:
    """检查测试覆盖率"""
    from app.tools.file_tools import run_shell
    return await run_shell(f"python -m pytest --cov={path} --cov-report=term-missing", ctx=ctx)
