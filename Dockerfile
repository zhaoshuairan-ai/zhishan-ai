# =====================================================================
# 智膳 AI · 单镜像部署（前端构建 + Flask 托管 + waitress）
# 构建：docker build -t food-safety-ai .
# 运行：docker run -p 8000:8000 -v fsai-data:/data --env-file .env food-safety-ai
# =====================================================================

# ---------- 阶段 1：构建前端 ----------
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json ./package.json
# 使用 npm 安装（不依赖本地 lockfile，保证构建可在任意机器复现）
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 阶段 2：Python 运行时 ----------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_ENV=production \
    SERVE_FRONTEND=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    DATA_DIR=/data \
    UPLOAD_DIR=/data/uploads

WORKDIR /app

# 先装依赖，利用 Docker 层缓存
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# 数据目录（SQLite 数据库 + 上传图片），生产环境务必挂载持久化卷
RUN mkdir -p /data/uploads
VOLUME ["/data"]

EXPOSE 8000

WORKDIR /app/backend

# 启动时幂等初始化数据库，再用 waitress 提供服务
CMD ["sh", "-c", "python init_db.py && waitress-serve --listen=0.0.0.0:8000 --threads=8 --channel-timeout=300 wsgi:app"]
