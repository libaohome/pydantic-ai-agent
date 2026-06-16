"""
项目一键启动脚本。

从仓库根目录执行 ``python scripts/start.py`` 时会依次：

1. 检查 Python 版本（需要 3.11+）
2. 若缺少 .env，从 .env.example 复制一份
3. 以可编辑模式安装项目及开发依赖（pip install -e '.[dev]'）
4. 运行 pytest（失败不阻断启动）
5. 启动 uvicorn，监听 0.0.0.0:8000

启动后可访问：
- Web UI: http://localhost:8000/ui
- API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health

面向小白：本脚本用 subprocess 调用 shell 命令，check=True 表示命令失败会抛异常。
"""

import os
import subprocess
import sys
from pathlib import Path


def run(cmd: str, check: bool = True) -> None:
    """
    在终端执行一条 shell 命令并打印命令本身。

    参数:
            cmd: 要执行的命令字符串
            check: True 时非零退出码会抛出 CalledProcessError
    """
    print(f"\n> {cmd}")
    subprocess.run(cmd, shell=True, check=check)


def main():
    """启动流程的主入口。"""
    # 脚本在 scripts/ 下，项目根目录是上一级
    project_root = Path(__file__).resolve().parent.parent
    os.chdir(project_root)

    print("=" * 60)
    print("  Pydantic AI Agent - Quick Start")
    print("=" * 60)

    # 1. 检查 Python 版本
    version = sys.version_info
    if version < (3, 11):
        print(f"[ERROR] Python 3.11+ required, got {version.major}.{version.minor}")
        sys.exit(1)
    print(f"[OK] Python {version.major}.{version.minor}.{version.micro}")

    # 2. 检查 .env 配置文件
    env_file = project_root / ".env"
    if not env_file.exists():
        print("[WARN] .env not found, copying from .env.example")
        example = project_root / ".env.example"
        if example.exists():
            import shutil
            shutil.copy(example, env_file)
            print("[OK] .env created from .env.example — please fill in your API keys")
    else:
        print("[OK] .env found")

    # 3. 安装依赖（可编辑安装，改代码即时生效）
    print("\n[1/3] Installing dependencies...")
    run("pip install -e '.[dev]'")

    # 4. 运行测试（check=False：测试失败仍继续启动，方便本地调试）
    print("\n[2/3] Running tests...")
    run("pytest tests/ -v --tb=short", check=False)

    # 5. 启动 ASGI 服务
    print("\n[3/3] Starting server...")
    print("\n" + "=" * 60)
    print("  Web UI:            http://localhost:8000/ui")
    print("  API available at:  http://localhost:8000")
    print("  Docs available at: http://localhost:8000/docs")
    print("  Health check:      http://localhost:8000/health")
    print("=" * 60)
    run("uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")


if __name__ == "__main__":
    main()
