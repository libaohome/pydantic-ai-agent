"""
Skill 集成模块 — 将 pydantic-ai-skills 与我们的 SkillPackageManager 整合。
提供两种集成方式：
  1. SkillsCapability（推荐） — 通过 Pydantic AI 的 capabilities 参数
  2. SkillsToolset — 通过 toolsets 参数（更底层控制）
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_ai import Agent, RunContext


def create_skills_capability(
    skills_dir: Path | str | None = None,
    extra_directories: list[Path | str] | None = None,
):
    """
    创建 SkillsCapability 实例（推荐方式）。

    用法:
        from app.skills import create_skills_capability

        agent = Agent(
            model='openai:gpt-5.2',
            instructions='You are a helpful assistant.',
            capabilities=[create_skills_capability('./skills')],
        )
    """
    from pydantic_ai_skills import SkillsCapability

    directories = []
    if skills_dir:
        directories.append(str(skills_dir))
    if extra_directories:
        directories.extend(str(d) for d in extra_directories)

    if not directories:
        # 默认使用 app/skills/ 目录
        directories.append(str(Path(__file__).parent))

    return SkillsCapability(directories=directories)


def create_skills_toolset(
    skills_dir: Path | str | None = None,
    extra_directories: list[Path | str] | None = None,
):
    """
    创建 SkillsToolset 实例（底层控制方式）。

    用法:
        from app.skills import create_skills_toolset

        toolset = create_skills_toolset('./skills')
        agent = Agent(
            model='openai:gpt-5.2',
            toolsets=[toolset],
        )
    """
    from pydantic_ai_skills import SkillsToolset

    directories = []
    if skills_dir:
        directories.append(str(skills_dir))
    if extra_directories:
        directories.extend(str(d) for d in extra_directories)

    if not directories:
        directories.append(str(Path(__file__).parent))

    return SkillsToolset(directories=directories, auto_reload=True)


def create_skill_aware_agent(
    model: str,
    instructions: str = "You are a helpful assistant.",
    skills_dir: Path | str | None = None,
    use_capability: bool = True,
    **agent_kwargs,
) -> Agent:
    """
    一步创建带 Skill 能力的 Agent。

    用法:
        from app.skills import create_skill_aware_agent

        agent = create_skill_aware_agent(
            model='openai:gpt-5.2',
            instructions='You are a coding assistant.',
            skills_dir='./skills',
        )

        result = await agent.run('帮我审查这段代码')
    """
    skills_path = skills_dir or Path(__file__).parent

    if use_capability:
        capability = create_skills_capability(skills_path)
        return Agent(
            model=model,
            instructions=instructions,
            capabilities=[capability],
            **agent_kwargs,
        )
    else:
        toolset = create_skills_toolset(skills_path)
        return Agent(
            model=model,
            instructions=instructions,
            toolsets=[toolset],
            **agent_kwargs,
        )
