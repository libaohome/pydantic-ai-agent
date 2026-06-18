"""知识问答 Agent — 基于知识库的智能问答。

本模块定义了一个知识问答助手 Agent，能够：
1. 搜索内部知识库和互联网获取信息
2. 加载并执行 Skills（可插拔技能包）中的脚本
3. 综合多源信息生成有据可查的回答
4. 返回 ``QaOutput`` 结构化结果（答案、来源、置信度、追问建议）

面向小白的关键概念：
- **capabilities**：Pydantic AI 的扩展点，通过 ``create_skills_capability()`` 挂载 Skills 能力。
- **Skills**：项目中的可扩展技能模块，Agent 可先 ``load_skill`` 再 ``run_skill_script``。
- **置信度**：模型对自身回答可靠程度的评估，0 表示完全不确定。
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent, RunContext

from app.core.deps import AgentDeps
from app.models.schemas import QaOutput
from app.skills.integration import create_skills_capability

# 使用 runner 默认行为：standard prompt、结构化 output 序列化、无 DB 会话
RUNTIME_CONFIG: dict[str, Any] = {}


# ─── Agent 定义 ──────────────────────────────────

qa_assistant_agent = Agent[AgentDeps, QaOutput](
    model="deepseek:deepseek-chat",
    output_type=QaOutput,
    deps_type=AgentDeps,
    retries=2,
    capabilities=[create_skills_capability()],
    instructions="""你是一名知识问答助手。你的任务：

1. 理解用户的问题并尽快给出最终结构化回答（QaOutput）
2. **天气问题**（气温、下雨、预报）：优先调用 `get_weather_forecast` 一次即可
   - 问「下周」「未来几天」：days=7
   - 问「明天」：tomorrow=true
   - 问「现在/今天」：默认 days=1
3. 其他 Skill 任务：先 `load_skill`，再 `run_skill_script`（**每个 skill 最多调用 1 次脚本**）
4. 知识库/联网仅作补充，各最多调用 1 次

**重要（避免死循环）：**
- 同一工具失败或结果已足够时，**不要重复调用**
- 禁止对同一问题反复 `load_skill` / `run_skill_script`
- 工具调用不超过 3 次后必须输出 QaOutput；无法确定则说明局限并降低置信度

回答要求：
- 准确、简洁、有据可查
- 必须标注信息来源
- 给出置信度评估
- 提供 2-3 个追问建议

如果找不到相关信息：
- 明确告知用户
- 置信度设为 0
- 建议用户咨询领域专家
""",
)


# ─── 注册工具 ──────────────────────────────────

@qa_assistant_agent.tool
async def get_weather_forecast(
    ctx: RunContext[AgentDeps],
    city: str,
    days: int = 1,
    tomorrow: bool = False,
) -> str:
    """查询城市天气与预报（无需 load_skill）。

    Args:
        city: 城市名，如「上海」「Beijing」
        days: 预报天数 1-7；用户问「下周」「未来几天」时用 7
        tomorrow: True 时仅返回明日预报（与 days 互斥时优先 tomorrow）

    Returns:
        JSON 字符串，含 daily 预报或 will_rain_in_period 等字段
    """
    import json

    from app.skills.weather.scripts.forecast import get_forecast

    if tomorrow:
        result = get_forecast(city, days=1, tomorrow=True)
    else:
        result = get_forecast(city, days=max(1, min(days, 7)))
    return json.dumps(result, ensure_ascii=False, indent=2)


@qa_assistant_agent.tool
async def search_kb(ctx: RunContext[AgentDeps], query: str, top_k: int = 5) -> str:
    """搜索内部知识库。

    Args:
        ctx: 运行上下文。
        query: 搜索关键词或自然语言问句。
        top_k: 返回最相关的前 k 条结果，默认 5。

    Returns:
        知识库检索结果的字符串。
    """
    from app.tools.kb_tools import search_knowledge_base
    return await search_knowledge_base(ctx, query, top_k)


@qa_assistant_agent.tool
async def search_internet(ctx: RunContext[AgentDeps], query: str) -> str:
    """搜索互联网以补充知识库未覆盖的信息。

    Args:
        ctx: 运行上下文。
        query: 搜索关键词。

    Returns:
        网页搜索结果的摘要字符串。
    """
    from app.tools.kb_tools import search_web
    return await search_web(ctx, query)
