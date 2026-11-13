# SDD — 容器化部署（container_deployment）

> **配置位置**：`docker-compose.yml`、`backend/Dockerfile`、`frontend/Dockerfile`、`frontend/nginx.conf`
> **定位**：把后端与前端打包为两个容器，供使用者克隆仓库后本地一键运行。

---

## 1. 功能描述

- `backend`：FastAPI 应用，内置嵌入式 Chroma 与 SQLite；启动前自动创建数据目录并执行 Alembic 迁移。
- `frontend`：Nginx 托管 Vite 构建产物，并把 `/api/` 反向代理到后端。
- 数据通过命名卷持久化：`backend_data`（SQLite 与上传文件）、`backend_chroma`（向量库）。
- 对外只发布前端端口（默认 8090），后端仅在 Compose 网络内暴露 8000。

约束：嵌入式 Chroma 与 SQLite 不适合多进程写，容器默认单 worker；本次只做本地构建，不推送镜像仓库。

---

## 2. 接口签名

### Compose 服务

```yaml
services:
  backend:
    image: qinghe-procurement-backend:local
    build: ./backend
    env_file: ./backend/.env        # 可选；缺失时使用默认配置
    environment:
      DATABASE_URL: sqlite+aiosqlite:////app/data/app.db
      UPLOAD_DIR: /app/data/uploads
      CHROMA_DIR: /app/chroma
      CHROMA_HTTP_HOST: ""          # 空值 = 嵌入式 Chroma
      UVICORN_WORKERS: "1"
    volumes: [backend_data:/app/data, backend_chroma:/app/chroma]
    expose: ["8000"]

  frontend:
    image: qinghe-procurement-frontend:local
    build: ./frontend
    ports: ["${APP_PORT:-8090}:80"]
    depends_on: {backend: {condition: service_healthy}}
```

### Nginx 路由

| 路径 | 行为 |
|:---- |:---- |
| `/` | `try_files $uri $uri/ /index.html`，支持 history 路由 |
| `/assets/` | 长缓存（构建产物带哈希） |
| `/api/` | 反向代理 `backend:8000`，关闭缓冲与缓存，读写超时 3600s |
| `/healthz` | 容器健康检查 |

上传请求体上限 `client_max_body_size 20m`，高于应用侧 `MAX_FILE_SIZE_MB=5`。

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| Docker Engine + Compose v2 | 构建与编排 |
| `python:3.11.10-slim-bookworm` | 后端运行时 |
| `node:20.18.0-alpine` | 前端构建 |
| `nginx:1.27.2-alpine` | 前端运行时与反向代理 |
| `backend/.env` | 模型 Key、JWT 密钥等运行配置（不入镜像、不入 Git） |

---

## 4. 异常处理

| 场景 | 处理 |
|:---- |:---- |
| `backend/.env` 不存在 | 使用代码默认值启动；JWT 为弱默认密钥，AI 功能不可用，文档要求先复制配置 |
| 端口被占用 | 通过 `APP_PORT` 覆盖前端宿主端口 |
| 迁移失败 | 容器启动失败并记录日志；`docker compose logs backend` 查看原因 |
| 数据目录权限 | 使用命名卷，镜像内预建目录并交给非 root 用户，避免宿主权限差异 |
| 多 worker 写冲突 | 默认 `UVICORN_WORKERS=1`；需要扩容时应改用 PostgreSQL 与独立 Chroma |
| SSE 被代理缓冲 | Nginx 关闭 `proxy_buffering`/`proxy_cache` 并放宽超时 |
| 上传 413 | `client_max_body_size` 已高于应用上限；超过应用上限时由后端返回 400 |
| arm64 依赖缺 wheel | 使用 `--platform linux/amd64` 构建 |
