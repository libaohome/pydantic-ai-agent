"""Agent 注册表 — 统一管理所有 Agent 实例"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic_ai import Agent

from app.core.deps import AgentDeps
from app.agents.code_reviewer import code_review_agent
from app.agents.data_analyst import data_analysis_agent
from app.agents.qa_assistant import qa_agent


class AgentName(str, Enum):
    code_reviewer = "code-reviewer"
    data_analyst = "data-analyst"
    qa_assistant = "qa-assistant"


# ─── Agent 注册表 ─────────────────────────────────

AGENTS: dict[AgentName, Agent[AgentDeps, Any]] = {
    AgentName.code_reviewer: code_review_agent,
    AgentName.data_analyst: data_analysis_agent,
    AgentName.qa_assistant: qa_agent,
}


def get_agent(name: str | AgentName) -> Agent[AgentDeps, Any]:
    """根据名称获取 Agent 实例"""
    if isinstance(name, str):
        name = AgentName(name)
    return AGENTS[name]


def list_agents() -> list[dict[str, str]]:
    """列出所有可用 Agent"""
    return [
        {
            "name": agent_name.value,
            "model": str(agent.model),
            "output_type": agent.output_type.__name__ if agent.output_type else "str",
        }
        for agent_name, agent in AGENTS.items()
    ]
