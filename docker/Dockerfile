# ─── 多阶段构建：依赖解析 + 生产镜像 ──────────

# Stage 1: 依赖安装
FROM python:3.12-slim AS builder

WORKDIR /build

# 先复制依赖声明，利用 Docker 缓存
COPY pyproject.toml .
RUN pip install --upgrade pip uv && \
    uv pip install --system . && \
    pip freeze > requirements-lock.txt

# Stage 2: 生产镜像
FROM python:3.12-slim

WORKDIR /app

# 安装运行时依赖
COPY --from=builder /build/requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt

# 复制应用代码
COPY app/ ./app/

# 创建数据目录
RUN mkdir -p /app/data

# 非 root 用户运行
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')"

# 启动
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
