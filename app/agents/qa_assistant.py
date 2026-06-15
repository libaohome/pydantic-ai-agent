"""知识问答 Agent — 基于知识库的智能问答"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext

from app.core.deps import AgentDeps
from app.core.llm import get_llm_manager
from app.models.schemas import QaOutput
from app.skills.integration import create_skills_toolset


# ─── Agent 定义 ──────────────────────────────────

qa_agent = Agent[AgentDeps, QaOutput](
    model=get_llm_manager().resolve_model_string("deepseek-chat"),
    output_type=QaOutput,
    deps_type=AgentDeps,
    toolsets=[create_skills_toolset()],
    instructions="""你是一名知识问答助手。你的任务：

1. 理解用户的问题
2. 若用户提到 skill，先 `load_skill`，再用 `run_skill_script` 执行脚本（**不要**用 `read_skill_resource` 读 `.py` 脚本）
3. `run_skill_script` 的 `script_name` 必须与 `load_skill` 返回的脚本名完全一致（如 `scripts/detect.py`）
3. 否则搜索内部知识库获取相关信息
4. 如需补充，可搜索互联网
5. 综合信息生成回答

回答要求：
- 准确、简洁、有据可查
- 必须标注信息来源
- 给出置信度评估
- 提供 2-3 个追问建议

如果知识库和互联网都找不到相关信息：
- 明确告知用户
- 置信度设为 0
- 建议用户咨询领域专家
""",
)


# ─── 注册工具 ──────────────────────────────────

@qa_agent.tool
async def search_kb(ctx: RunContext[AgentDeps], query: str, top_k: int = 5) -> str:
    """搜索内部知识库"""
    from app.tools.kb_tools import search_knowledge_base
    return await search_knowledge_base(ctx, query, top_k)


@qa_agent.tool
async def search_internet(ctx: RunContext[AgentDeps], query: str) -> str:
    """搜索互联网"""
    from app.tools.kb_tools import search_web
    return await search_web(ctx, query)
