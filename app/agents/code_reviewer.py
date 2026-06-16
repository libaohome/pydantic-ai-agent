"""代码审查 Agent — 结构化代码审查，返回类型安全的审查报告。

本模块定义了一个专门做代码审查的 AI Agent，具备以下能力：
1. 接收用户提交的代码或审查类问题
2. 从正确性、安全性、性能、可维护性等维度分析
3. 通过工具读取文件、运行 linter、检查测试覆盖率（仅在有具体代码时）
4. 返回 ``CodeReviewOutput`` 结构化结果（问题列表、评分、是否通过等）

面向小白的关键概念：
- **pydantic-ai Agent**：用 ``Agent[DepsType, OutputType]`` 声明依赖和输出类型。
- **instructions**：系统提示词，告诉模型扮演什么角色、遵循什么规则。
- **@agent.tool 装饰器**：把普通 async 函数注册为 Agent 可调用的工具。
- **RunContext**：工具执行时的上下文，内含 ``deps``（依赖注入对象）等信息。
"""

from __future__ import annotations

import logfire  # 可观测性库，用于记录 span（追踪片段），便于调试和监控

from pydantic_ai import Agent, RunContext

from app.core.deps import AgentDeps
from app.core.llm import get_llm_manager  # 单例 LLM 管理器，负责解析模型别名
from app.models.schemas import CodeReviewOutput  # Pydantic 模型，定义审查报告的结构

# 当用户没有提供具体代码时，追加这段系统提示，引导模型直接作答而非盲目调用工具
_NO_CODE_HINT = (
    "[系统提示] 用户未提供具体源代码或文件路径。"
    "请直接基于专业知识输出审查要点（结构化 CodeReviewOutput），"
    "不要调用 read_source_file、run_linter、check_test_coverage 等工具。"
    "issues 可列出通用检查项（line 填 0），summary 给出完整指南。"
)


def prepare_review_input(user_input: str) -> str:
    """预处理审查输入：无具体代码时引导 Agent 直接作答。

    若用户只问了方法论（如「Spring Boot 项目审查要点」）而没有贴代码，
    则在输入末尾追加 ``_NO_CODE_HINT``，避免 Agent 盲目调用 Shell 类工具。

    Args:
        user_input: 用户原始输入文本。

    Returns:
        原样返回或追加提示后的输入字符串。
    """
    text = user_input.strip()  # 去掉首尾空白
    if not text:
        return user_input  # 空输入直接返回，不做处理

    # 检测 Markdown 代码块标记
    has_code_block = "```" in text
    # ``any(... for marker in (...))``：生成器表达式，任一 marker 出现在 text 中即为 True
    has_file_ref = any(
        marker in text
        for marker in (".java", ".kt", ".py", ".go", "src/", "pom.xml", "build.gradle")
    )
    # 大段粘贴代码（多行且含典型代码特征）
    looks_like_code = text.count("\n") >= 8 and any(
        kw in text for kw in ("class ", "def ", "function ", "public ", "import ", "{")
    )

    # 任一条件满足，说明用户提供了可审查的代码，无需追加提示
    if has_code_block or has_file_ref or looks_like_code:
        return user_input

    # f-string：在字符串前加 f，花括号内可嵌入变量或表达式
    return f"{user_input}\n\n{_NO_CODE_HINT}"


# ─── Agent 定义 ──────────────────────────────────
# Agent[AgentDeps, CodeReviewOutput] 表示：
#   - deps_type=AgentDeps：运行时注入租户、用户等上下文
#   - output_type=CodeReviewOutput：模型输出会被解析为 Pydantic 对象

code_review_agent = Agent[AgentDeps, CodeReviewOutput](
    model=get_llm_manager().resolve_model_string("deepseek-chat"),  # 默认使用 deepseek-chat 模型
    output_type=CodeReviewOutput,
    deps_type=AgentDeps,
    instructions="""你是一名资深代码审查工程师。你的任务：

1. 仔细审查用户提交的代码，或回答代码审查方法论/检查清单类问题
2. 从以下维度评估：
   - 代码正确性：逻辑错误、边界条件、异常处理
   - 安全性：注入攻击、数据泄露、权限问题
   - 性能：时间/空间复杂度、N+1 查询、内存泄漏
   - 可维护性：命名规范、函数长度、圈复杂度
   - 最佳实践：设计模式、SOLID 原则、DRY

3. 每个问题必须给出：
   - 精确的行号（无具体代码时 line 填 0）
   - 严重程度（critical / warning / info）
   - 清晰的问题描述
   - 可操作的修复建议

4. 给出总体质量评分（0-100）和是否通过的判断

注意：
- 若用户仅询问审查要点/最佳实践（如 Spring Boot 项目），直接基于经验作答，**不要调用任何工具**
- 仅当用户提供了具体代码片段或明确文件路径时，才使用 read_file / run_shell
- run_shell 仅支持白名单命令：git, python, pip, npm, node, ls, cat, grep, find 等
- 审查要严格但不吹毛求疵，info 级别留给风格偏好
""",
)


# ─── 注册工具 ──────────────────────────────────
# ``@code_review_agent.tool`` 装饰器把下面的 async 函数注册为该 Agent 的工具。
# 模型在需要时会自动决定调用哪个工具，并传入参数。

@code_review_agent.tool
async def read_source_file(ctx: RunContext[AgentDeps], path: str) -> str:
    """读取源代码文件内容。

    Args:
        ctx: pydantic-ai 运行上下文，``ctx.deps`` 可访问 ``AgentDeps``。
        path: 要读取的文件路径。

    Returns:
        文件内容的字符串。
    """
    # 延迟导入：仅在工具被调用时才加载模块，避免循环依赖、加快启动
    from app.tools.file_tools import read_file
    return await read_file(path, ctx=ctx)


@code_review_agent.tool
async def run_linter(ctx: RunContext[AgentDeps], command: str) -> str:
    """运行代码检查工具（linter）。

    仅支持白名单命令：ruff、mypy、eslint 等（通过 python/npm 调用）。

    Args:
        ctx: 运行上下文。
        command: 要执行的 shell 命令字符串。

    Returns:
        命令的标准输出或错误信息。
    """
    from app.tools.file_tools import run_shell
    # ``with logfire.span(...)``：创建一个可追踪的 span，记录本次 linter 调用
    with logfire.span("run_linter", command=command):
        return await run_shell(command, ctx=ctx)


@code_review_agent.tool
async def check_test_coverage(ctx: RunContext[AgentDeps], path: str) -> str:
    """检查指定路径的测试覆盖率。

    内部通过 pytest 的 ``--cov`` 选项生成覆盖率报告。

    Args:
        ctx: 运行上下文。
        path: 要统计覆盖率的代码路径。

    Returns:
        pytest 覆盖率报告的终端输出。
    """
    from app.tools.file_tools import run_shell
    return await run_shell(f"python -m pytest --cov={path} --cov-report=term-missing", ctx=ctx)
