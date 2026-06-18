"""Agent 注册表 — 统一管理所有 Agent 实例。

本模块是整个 Agent 系统的「电话簿」：把各个业务 Agent（代码审查、数据分析、知识问答）
集中登记在一个字典里，对外提供按名称查找和列表查询的能力。

面向小白的关键概念：
- **Agent**：由 pydantic-ai 框架创建的 AI 智能体，封装了模型、指令和工具。
- **Enum（枚举）**：用一组固定常量表示有限选项，避免手写字符串拼错。
- **泛型类型注解** ``Agent[AgentDeps, Any]``：告诉类型检查器该 Agent 的依赖类型和输出类型。
- **注册表模式**：新增 Agent 时只需在此文件导入并加入 ``AGENTS`` 字典即可。
"""

from __future__ import annotations

from enum import Enum  # Enum：枚举基类，用于定义一组命名常量
from typing import Any  # Any：表示「任意类型」，常用于输出类型不确定的场景

from pydantic_ai import Agent  # pydantic-ai 的核心 Agent 类

from app.core.deps import AgentDeps  # 自定义依赖注入容器（租户、用户、请求 ID 等）
from app.agents.code_reviewer import RUNTIME_CONFIG as code_reviewer_runtime, code_review_agent
from app.agents.data_analyst import RUNTIME_CONFIG as data_analyst_runtime, data_analysis_agent
from app.agents.qa_assistant import RUNTIME_CONFIG as qa_assistant_runtime, qa_assistant_agent
from app.agents.chat_model import (
    RUNTIME_CONFIG as chat_model_runtime,
    chat_model_agent,
)
from app.agents.image_gen import (
    RUNTIME_CONFIG as image_gen_runtime,
    image_gen_agent,
)


class AgentName(str, Enum):
    """Agent 名称枚举。

    继承 ``str`` 和 ``Enum`` 后，每个成员既是枚举值，也可以当普通字符串使用
    （例如 ``AgentName.code_reviewer == "code-reviewer"`` 为真）。

    成员名（左侧）是 Python 标识符；``.value``（右侧字符串）是对外 API 使用的名称。
    """

    code_reviewer = "code-reviewer"   # 代码审查 Agent
    data_analyst = "data-analyst"     # 数据分析 Agent
    qa_assistant = "qa-assistant"     # 知识问答 Agent
    chat_model = "chat-model"         # 通用对话（文本 / 多模态理解）
    image_gen = "image-gen"           # 文生图


# ─── Agent 注册表 ─────────────────────────────────
# 字典的 key 是 AgentName 枚举，value 是对应的 Agent 实例。
# 类型注解 ``dict[AgentName, Agent[AgentDeps, Any]]`` 说明：
#   - key：AgentName 枚举成员
#   - value：依赖类型为 AgentDeps、输出类型为 Any 的 Agent 对象

AGENTS: dict[AgentName, Agent[AgentDeps, Any]] = {
    AgentName.code_reviewer: code_review_agent,
    AgentName.data_analyst: data_analysis_agent,
    AgentName.qa_assistant: qa_assistant_agent,
    AgentName.chat_model: chat_model_agent,
    AgentName.image_gen: image_gen_agent,
}

AGENT_RUNTIME_CONFIGS: dict[AgentName, dict[str, Any]] = {
    AgentName.code_reviewer: code_reviewer_runtime,
    AgentName.data_analyst: data_analyst_runtime,
    AgentName.qa_assistant: qa_assistant_runtime,
    AgentName.chat_model: chat_model_runtime,
    AgentName.image_gen: image_gen_runtime,
}


def build_runtime_config(agent_name: AgentName, user_config: dict[str, Any]) -> dict[str, Any]:
    """合并 Agent 模块声明的 RUNTIME_CONFIG 与外层请求传入的配置（后者可覆盖）。"""
    defaults = AGENT_RUNTIME_CONFIGS.get(agent_name, {})
    return {**defaults, **user_config}

def get_agent(name: AgentName) -> Agent[AgentDeps, Any]:
    """根据名称获取 Agent 实例。

    Args:
        name: ``AgentName`` 枚举。

    Returns:
        对应的 pydantic-ai ``Agent`` 实例。

    Raises:
        ValueError: 当字符串名称不在 ``AgentName`` 枚举中时由 ``AgentName(name)`` 抛出。
        KeyError: 当枚举值在 ``AGENTS`` 字典中不存在时抛出。
    """
    return AGENTS[name]

def list_agents() -> list[dict[str, str]]:
    """列出所有可用 Agent 的元信息。

    遍历注册表，提取每个 Agent 的名称、模型和输出类型，供 API 列表接口使用。

    Returns:
        字典列表，每项包含 ``name``、``model``、``output_type`` 三个字符串字段。
    """
    return [
        {
            "name": agent_name,  # 枚举的字符串值，如 "code-reviewer"
            "model": str(agent.model),  # Agent 绑定的 LLM 模型标识
            # 若有结构化输出类型则取类名，否则默认为普通字符串 "str"
            # "output_type": 只有 type 才有 __name__。
            "output_type": agent.output_type.__name__ if isinstance(agent.output_type, type) else type(agent.output_type).__name__
        }
        for agent_name, agent in AGENTS.items()  # 字典推导式：遍历 key-value 对
    ]
