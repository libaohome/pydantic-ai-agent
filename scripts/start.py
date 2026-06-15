"""快速启动脚本 — 验证环境、安装依赖、启动服务"""

import os
import subprocess
import sys
from pathlib import Path


def run(cmd: str, check: bool = True) -> None:
    print(f"\n> {cmd}")
    subprocess.run(cmd, shell=True, check=check)


def main():
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

    # 2. 检查 .env
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

    # 3. 安装依赖
    print("\n[1/3] Installing dependencies...")
    run("pip install -e '.[dev]'")

    # 4. 运行测试
    print("\n[2/3] Running tests...")
    run("pytest tests/ -v --tb=short", check=False)

    # 5. 启动服务
    print("\n[3/3] Starting server...")
    print("\n" + "=" * 60)
    print("  API available at: http://localhost:8000")
    print("  Docs available at: http://localhost:8000/docs")
    print("  Health check:      http://localhost:8000/health")
    print("=" * 60)
    run("uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")


if __name__ == "__main__":
    main()
