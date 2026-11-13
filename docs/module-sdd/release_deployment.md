# SDD — 青禾智采源码发布与首次部署

## 功能描述

以目标仓库现有 main 为基线发布干净源码快照，保留后端、前端、测试、迁移、CI 与必要设计文档；不发布本地历史、数据库、知识库数据、上传资料、评测产物和代理配置。

首次部署先创建数据目录并执行 Alembic，再启动服务。SQLite 使用显式异步队列池，使 requirements.txt 锁定版本支持现有连接池参数。标准部署入口为 Docker Compose；无 Docker 环境时可按本地方式运行。

## 接口签名

业务接口与 Pydantic 通信模型不变。容器部署入口为 `docker compose up -d --build`（先复制 `.env.example` 为 `backend/.env`）；本地入口为 `python -m alembic upgrade head`、`python -m uvicorn app.main:app` 和 `npm run dev`。Alembic 从 Settings.DATABASE_URL 读取目标地址。

## 外部依赖

使用现有 Python 3.11、Node.js 20、Docker Engine 与 Compose、SQLite、Chroma 与项目依赖，不新增外部库。AI 能力需要用户在服务端配置实际可用的 OpenAI 兼容模型及嵌入服务。

## 异常处理与验收

依赖安装、数据库迁移或测试失败时先修复再发布。密钥扫描仅报告文件位置，不输出密钥值。验证后端全量测试、前端测试/构建、全新数据库迁移、容器构建与健康检查、注册登录流程。真实模型调用须单独配置并验收。
