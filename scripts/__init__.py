"""
scripts 包 — 存放项目运维与启动脚本。

将 scripts 声明为 Python 包（含本 __init__.py）后，
可从项目根目录用 ``python -m scripts.start`` 等方式调用。

当前主要脚本：
- start.py — 环境检查、安装依赖、运行测试并启动 uvicorn
"""
