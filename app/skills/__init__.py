"""
app.skills — Skill 动态加载与 ZIP 包管理

核心组件：
  - SkillPackageManager: ZIP 上传、解压、安全扫描、版本管理
  - create_skills_capability: 创建 SkillsCapability（推荐集成方式）
  - create_skills_toolset: 创建 SkillsToolset（底层控制方式）
  - create_skill_aware_agent: 一步创建带 Skill 能力的 Agent

依赖：
  pip install pydantic-ai-skills
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
