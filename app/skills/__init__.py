"""
app.skills 包 — Skill 动态加载与 ZIP 包管理。

本包是项目中 Skill 子系统的统一对外入口，包含：

核心组件
--------
- **SkillPackageManager**: ZIP 上传、解压、安全扫描、manifest 版本管理
- **create_skills_capability**: 创建 SkillsCapability（推荐 Agent 集成方式）
- **create_skills_toolset**: 创建 SkillsToolset（底层 toolset 集成）
- **create_skill_aware_agent**: 一步创建带 Skill 能力的 Agent

数据模型（也可从 manager 子模块导入）
--------------------------------------
- UploadResult / SkillListResult: API 与 UI 使用的响应结构

依赖
----
pip install pydantic-ai-skills

典型用法::

        from app.skills import SkillPackageManager, create_skill_aware_agent

        manager = SkillPackageManager()
        agent = create_skill_aware_agent(model="openai:gpt-4o")
"""

from app.skills.manager import SkillPackageManager, UploadResult, SkillListResult
from app.skills.integration import (
    create_skills_capability,
    create_skills_toolset,
    create_skill_aware_agent,
)

__all__ = [
    "SkillPackageManager",
    "UploadResult",
    "SkillListResult",
    "create_skills_capability",
    "create_skills_toolset",
    "create_skill_aware_agent",
]
