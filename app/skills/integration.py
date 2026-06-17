"""
Skill 与 Pydantic AI Agent 的集成模块。

将 pydantic-ai-skills 库与项目内的 SkillPackageManager 目录对齐，
提供三种便捷工厂函数：

1. create_skills_capability（推荐）
      - 通过 Agent 的 capabilities 参数挂载
      - Agent 会自动获得「读取并遵循 SKILL.md」的能力

2. create_skills_toolset
      - 更底层的 toolsets 方式，可配合 auto_reload

3. create_skill_aware_agent
      - 一步创建已启用 Skill 的 Agent 实例

依赖: pip install pydantic-ai-skills

面向小白：
- Capability 是 Pydantic AI 的扩展点，类似「给 Agent 装插件」
- skills_dir 默认指向 app/skills/，与 ZIP 上传安装目录一致
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent


def create_skills_capability(
    skills_dir: Path | str | None = None,
    extra_directories: list[Path | str] | None = None,
):
    """
    创建 SkillsCapability 实例（推荐集成方式）。

    SkillsCapability 会让 Agent 在需要时加载 skills 目录下的 SKILL.md，
    并按其中的指令扩展行为。

    参数:
            skills_dir: 主 Skill 目录；None 时使用 app/skills/
            extra_directories: 额外的 Skill 搜索路径列表

    返回:
            pydantic_ai_skills.SkillsCapability 实例

    用法示例::

            from app.skills import create_skills_capability

            agent = Agent(
                    model='deepseek:deepseek-chat',
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
        # 默认使用本文件所在的 app/skills/ 目录
        directories.append(str(Path(__file__).parent))

    return SkillsCapability(directories=directories)


def create_skills_toolset(
    skills_dir: Path | str | None = None,
    extra_directories: list[Path | str] | None = None,
):
    """
    创建 SkillsToolset 实例（底层、可精细控制）。

    与 Capability 相比，Toolset 直接暴露为 Agent 的工具集，
    适合需要 auto_reload 或与其他 toolset 组合的场景。

    参数:
            skills_dir: 主 Skill 目录
            extra_directories: 额外目录

    返回:
            pydantic_ai_skills.SkillsToolset 实例（auto_reload=True）

    用法示例::

            from app.skills import create_skills_toolset

            toolset = create_skills_toolset('./skills')
            agent = Agent(
                    model='deepseek:deepseek-chat',
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
    **agent_kwargs,
) -> Agent:
    """一步创建已集成 Skill capabilities 的 Agent。"""
    skills_path = skills_dir or Path(__file__).parent
    capability = create_skills_capability(skills_path)
    return Agent(
        model=model,
        instructions=instructions,
        capabilities=[capability],
        **agent_kwargs,
    )
