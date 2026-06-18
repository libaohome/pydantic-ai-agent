"""应用入口模块 — FastAPI 应用创建与生命周期管理。

本文件位于项目 ``app/`` 包根目录，是整个 Web 服务的**启动入口**。

职责概览：
    - 创建并配置 FastAPI 应用实例（``create_app``）
    - 注册 API 路由、CORS 中间件、Gradio 管理界面
    - 在应用启动/关闭时执行初始化与清理（``lifespan``）

在项目中的位置::

    pydantic-ai-agent/
    └── app/
        ├── main.py          ← 当前文件（应用入口）
        ├── api/             ← REST API 路由
        ├── core/            ← 配置、数据库、LLM 等核心模块
        ├── ui/              ← Gradio Web 界面
        └── skills/          ← Skill 包管理

启动方式：
    - 开发：``python -m app.main`` 或 ``uvicorn app.main:app --reload``
    - 生产：由 ``scripts/start.py`` 或进程管理器加载 ``app.main:app``
"""

# ``from __future__ import annotations`` 让类型注解可以写成字符串形式，
# 并支持 ``X | Y`` 联合类型写法，且避免循环导入问题。
from __future__ import annotations

# ``asynccontextmanager`` 是装饰器，把异步生成器函数变成异步上下文管理器，
# 常用于 FastAPI 的 lifespan（启动/关闭钩子）。
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.routes import router as agent_router
from app.core.config import get_settings
from app.core.deps import init_db
from app.core.observability import setup_observability
from app.skills.manager import SkillPackageManager
from app.skills.routes import router as skill_router
from app.skills.routes import set_skill_manager
from app.ui.gradio_app import mount_gradio_ui


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器：在 FastAPI 启动和关闭时自动执行。

    FastAPI 通过 ``lifespan`` 参数接收此函数。``yield`` 之前是**启动逻辑**，
    ``yield`` 之后是**关闭逻辑**（类似 try/finally）。

    Args:
        app: FastAPI 应用实例（由框架注入，此处未直接使用但签名必须保留）。

    Yields:
        None: ``yield`` 表示应用已就绪，可以开始处理请求。
    """
    settings = get_settings()

    # ─── 启动阶段 ───
    print(f"[Startup] Environment: {settings.app_env}")
    setup_observability(app)
    # ``await`` 等待异步函数完成；数据库初始化是 I/O 操作，用 async 不阻塞事件循环。
    await init_db()
    print("[Startup] Database initialized")

    from app.core.llm_manager import get_llm_manager
    print(f"[Startup] LLM models loaded: {len(get_llm_manager().list_aliases())} model(s)")

    # 初始化 Skill 包管理器，并注入到 skills 路由模块的全局变量中
    skill_manager = SkillPackageManager()
    set_skill_manager(skill_manager)
    installed = skill_manager.list_installed()
    print(f"[Startup] Skills loaded: {installed.total} skill(s) installed")
    print("[Startup] Agent API + Skill Upload ready")

    # 应用运行期间挂起在此；收到关闭信号后继续执行下方代码
    yield

    # ─── 关闭阶段 ───
    print("[Shutdown] Cleaning up...")


def create_app() -> FastAPI:
    """工厂函数：创建并配置 FastAPI 应用实例。

    采用工厂模式而非直接写全局 ``app``，便于测试时创建独立实例。

    Returns:
        FastAPI: 配置完成的应用对象，可被 uvicorn 或 ASGI 服务器加载。
    """
    settings = get_settings()

    # FastAPI() 创建 ASGI 应用；``lifespan`` 绑定上面的生命周期函数
    app = FastAPI(
        title="Pydantic AI Agent Service",
        description="Production-grade AI Agent built with Pydantic AI",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS（跨域资源共享）中间件：允许浏览器从不同域名访问 API
    # ``add_middleware`` 按「后添加先执行」顺序包装请求处理链
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ``include_router`` 将子路由模块挂到主应用，``prefix`` 统一加 URL 前缀
    app.include_router(agent_router, prefix="/api/v1")
    app.include_router(skill_router, prefix="/api/v1")

    # 在函数内部用 ``@app.get`` 定义路由，称为**嵌套路由**或**局部路由**
    # ``include_in_schema=False`` 表示不出现在 OpenAPI/Swagger 文档里
    @app.get("/", include_in_schema=False)
    async def root():
        """根路径：重定向到 Gradio 管理界面。"""
        return RedirectResponse(url="/ui/")

    @app.get("/health")
    async def health():
        """健康检查端点，供负载均衡或监控系统探测服务是否存活。"""
        return {"status": "ok", "version": "0.1.0"}

    # 挂载 Gradio 子应用（Chat / Agent / Model / Skills 管理界面）
    mount_gradio_ui(app, path="/ui")

    return app


# 模块级单例：uvicorn 通过字符串 ``"app.main:app"`` 加载此对象
app = create_app()


# ``if __name__ == "__main__"``：仅当直接运行本文件时执行（``python app/main.py``）
if __name__ == "__main__":
    import uvicorn
    # ``reload=True`` 开发模式下文件变更自动重启（生产环境应关闭）
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # 监听所有网卡；0.0.0.0 表示接受外部连接
        port=8000,
        reload=True,
    )
