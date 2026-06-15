"""
Skill 上传 API 路由 — 提供 ZIP 上传、列表查询、卸载等 REST 接口。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, Query
from pydantic import BaseModel

from app.skills.manager import SkillPackageManager, SkillListResult, UploadResult


router = APIRouter(prefix="/skills", tags=["skills"])

# 共享的 SkillPackageManager 实例（在 main.py 中初始化后注入）
_manager: SkillPackageManager | None = None


def set_skill_manager(manager: SkillPackageManager) -> None:
    global _manager
    _manager = manager


def get_skill_manager() -> SkillPackageManager:
    if _manager is None:
        raise HTTPException(status_code=500, detail="SkillPackageManager not initialized")
    return _manager


# ─── 请求/响应模型 ────────────────────────────

class UninstallRequest(BaseModel):
    skill_name: str


class UninstallResponse(BaseModel):
    success: bool
    message: str


# ─── 路由 ──────────────────────────────────────

@router.post("/upload", response_model=UploadResult)
async def upload_skill(
    file: UploadFile = File(..., description="Skill ZIP 包"),
    uploaded_by: str = Query(default="anonymous", description="上传者标识"),
    allow_warnings: bool = Query(default=True, description="是否允许有安全警告的包"),
):
    """
    上传 Skill ZIP 包。

    ZIP 包结构要求：
    ```
    my-skill.zip
    └── my-skill/
        ├── SKILL.md      (必需 — YAML frontmatter + Markdown 指令)
        ├── scripts/      (可选 — Python/Shell 脚本)
        └── resources/    (可选 — 参考文档/数据文件)
    ```

    SKILL.md frontmatter 必需字段：
    - name: 小写字母+数字+连字符，1-64字符
    - description: 技能描述，最长 1024 字符
    """
    # 验证文件类型
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    # 读取 ZIP 内容
    zip_bytes = await file.read()
    if len(zip_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty ZIP file")

    # 大小限制（100MB）
    if len(zip_bytes) > 100 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="ZIP file too large (max 100MB)")

    # 调用管理器处理上传
    manager = get_skill_manager()
    result = await manager.upload(
        zip_bytes=zip_bytes,
        uploaded_by=uploaded_by,
        allow_warnings=allow_warnings,
    )

    if not result.success:
        raise HTTPException(status_code=422, detail=result.message)

    return result


@router.get("/list", response_model=SkillListResult)
async def list_skills():
    """列出所有已安装的 Skill"""
    manager = get_skill_manager()
    return manager.list_installed()


@router.delete("/uninstall", response_model=UninstallResponse)
async def uninstall_skill(request: UninstallRequest):
    """卸载指定 Skill"""
    manager = get_skill_manager()

    try:
        success = manager.uninstall(request.skill_name)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    if not success:
        raise HTTPException(status_code=404, detail=f"Skill '{request.skill_name}' not found")

    return UninstallResponse(
        success=True,
        message=f"Skill '{request.skill_name}' uninstalled successfully.",
    )


@router.get("/directory")
async def get_skills_directory():
    """获取当前 skills 目录路径（供调试/运维使用）"""
    manager = get_skill_manager()
    return {"skills_directory": str(manager.get_skills_directory())}
