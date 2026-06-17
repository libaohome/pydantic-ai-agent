"""ChatModelAgent — 仅依赖大模型原生能力的通用对话 Agent。

不挂载 Skill、知识库、天气等业务工具；当前仅使用 DeepSeek 文本对话能力。
"""

from __future__ import annotations

from pydantic_ai import Agent

from app.core.deps import AgentDeps
from app.core.llm import get_llm_manager

chat_model_agent = Agent[AgentDeps, str](
    model=get_llm_manager().resolve_model_string("deepseek-chat"),
    output_type=str,
    deps_type=AgentDeps,
    instructions="""你是一个通用对话助手，只使用当前大模型本身的能力：

1. **文本**：自然、清晰地回答用户问题。
2. **附件**：文本类文件可结合内容作答；若当前模型支持多模态（如 sensenova-6.7-flash-lite），可理解图片。
3. **生图**：若使用 sensenova-u1-fast，将根据文字描述生成图片。

约束：
- 不要使用 Skill、知识库检索、天气脚本或任何外部业务工具（你没有这些能力）。
- 不要假装调用了不存在的工具。
- 使用与用户相同的语言回复。
""",
)
