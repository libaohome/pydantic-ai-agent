"""应用入口 — FastAPI 应用创建与生命周期"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.observability import setup_observability
from app.core.deps import init_db
from app.api.routes import router as agent_router
from app.skills.manager import SkillPackageManager
from app.skills.routes import router as skill_router, set_skill_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动 & 关闭"""
    settings = get_settings()

    # ─── 启动 ───
    print(f"[Startup] Environment: {settings.app_env}")
    setup_observability(app)
    await init_db()
    print("[Startup] Database initialized")

    # 初始化 Skill 包管理器
    skill_manager = SkillPackageManager()
    set_skill_manager(skill_manager)
    installed = skill_manager.list_installed()
    print(f"[Startup] Skills loaded: {installed.total} skill(s) installed")
    print("[Startup] Agent API + Skill Upload ready")

    yield

    # ─── 关闭 ───
    print("[Shutdown] Cleaning up...")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    settings = get_settings()

    app = FastAPI(
        title="Pydantic AI Agent Service",
        description="Production-grade AI Agent built with Pydantic AI",
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 路由
    app.include_router(agent_router, prefix="/api/v1")
    app.include_router(skill_router, prefix="/api/v1")

    # 根路径 → API 文档
    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/docs")

    # 健康检查
    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
