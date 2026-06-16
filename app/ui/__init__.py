"""
Gradio Web UI 子包（app.ui）。

对外暴露两个入口函数：
- create_gradio_demo: 仅构建 Gradio Blocks，不启动服务
- mount_gradio_ui: 将界面挂到 FastAPI 的指定路径（如 /ui）

典型用法（在 app/main.py 中）::

        from app.ui import mount_gradio_ui
        mount_gradio_ui(app, path="/ui")
"""

from app.ui.gradio_app import create_gradio_demo, mount_gradio_ui

__all__ = ["create_gradio_demo", "mount_gradio_ui"]
