"""
Skill 管理 REST API 路由模块。

将 SkillPackageManager 的能力暴露为 HTTP 接口，挂载在 FastAPI 应用下：
- POST   /skills/upload     — 上传 ZIP 安装 Skill
- GET    /skills/list       — 列出已安装 Skill
- DELETE /skills/uninstall  — 卸载指定 Skill
- GET    /skills/directory  — 查看 skills 目录路径（调试用）

SkillPackageManager 实例在 app/main.py 启动时创建，并通过 set_skill_manager() 注入本模块。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, Query
from pydantic import BaseModel

from app.skills.manager import SkillPackageManager, SkillListResult, UploadResult


# 创建子路由，前缀 /skills，OpenAPI 标签为 skills
router = APIRouter(prefix="/skills", tags=["skills"])

# 全局单例：由 main.py 在应用启动时注入
_manager: SkillPackageManager | None = None


def set_skill_manager(manager: SkillPackageManager) -> None:
    """
    注入 SkillPackageManager 实例（应用启动时调用一次）。

    参数:
            manager: 已配置好 skills_dir 的管理器实例
    """
    global _manager
    _manager = manager


def get_skill_manager() -> SkillPackageManager:
    """
    获取当前 Skill 管理器。

    若尚未调用 set_skill_manager，返回 HTTP 500。
    """
    if _manager is None:
        raise HTTPException(status_code=500, detail="SkillPackageManager not initialized")
    return _manager


# ─── 请求/响应模型 ────────────────────────────

class UninstallRequest(BaseModel):
    """卸载接口的请求体。"""

    skill_name: str


class UninstallResponse(BaseModel):
    """卸载接口的响应体。"""

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
    上传 Skill ZIP 包并安装。

    ZIP 包结构要求:
            my-skill.zip
            └── my-skill/
                    ├── SKILL.md      (必需 — YAML frontmatter + Markdown 指令)
                    ├── scripts/      (可选 — Python/Shell 脚本)
                    └── resources/    (可选 — 参考文档/数据文件)

    SKILL.md frontmatter 必需字段:
    - name: 小写字母+数字+连字符，1-64 字符
    - description: 技能描述，最长 1024 字符
    """
    # 仅接受 .zip 扩展名
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    zip_bytes = await file.read()
    if len(zip_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty ZIP file")

    # 硬限制 100MB，与 SecurityScanner 的单文件阈值策略一致
    if len(zip_bytes) > 100 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="ZIP file too large (max 100MB)")

    manager = get_skill_manager()
    result = await manager.upload(
        zip_bytes=zip_bytes,
        uploaded_by=uploaded_by,
        allow_warnings=allow_warnings,
    )

    # 业务失败用 422，便于客户端区分「请求格式对但内容不合格」
    if not result.success:
        raise HTTPException(status_code=422, detail=result.message)

    return result


@router.get("/list", response_model=SkillListResult)
async def list_skills():
    """列出所有已安装 Skill 及其 manifest 元数据。"""
    manager = get_skill_manager()
    return manager.list_installed()


@router.delete("/uninstall", response_model=UninstallResponse)
async def uninstall_skill(request: UninstallRequest):
    """
    卸载指定 Skill。

    成功返回 UninstallResponse；不存在返回 404；路径攻击返回 403。
    """
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
    """返回当前 skills 根目录的绝对路径字符串（运维/调试）。"""
    manager = get_skill_manager()
    return {"skills_directory": str(manager.get_skills_directory())}
