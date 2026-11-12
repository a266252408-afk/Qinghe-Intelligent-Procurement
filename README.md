# 青禾智采

面向园林工程采购的 AI 辅助采购平台。通过对话连接清单解析、询价、报价比价、审批与收货流程，由采购员确认业务决策。

## 功能

- 管理员与采购员注册登录、团队邀请、成员权限和团队数据隔离。
- 项目与采购清单管理，支持自然语言及文件清单解析。
- 询价单生成、供应商报价录入与解析、确定性多维评分及 AI 比价建议。
- 审批、供应商订单、收货登记与历史物料价格查询。
- 行业知识库、BM25 与向量混合检索、带来源的知识问答。
- SSE 流式对话、工具调度、会话历史和模型调用日志。

## 技术栈

后端：Python 3.11、FastAPI、Pydantic、SQLAlchemy 异步 ORM、SQLite、Alembic、LangChain、Chroma。

前端：Vue 3、Vite、Pinia、Element Plus、ECharts。

## 本地开发

需要 Python 3.11、Node.js 20 和 npm。以下命令在仓库根目录执行，Windows 使用 PowerShell。

```powershell
git clone https://github.com/a266252408-afk/Qinghe-Intelligent-Procurement.git
cd Qinghe-Intelligent-Procurement
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
Copy-Item .env.example backend/.env
```

编辑 `backend/.env`：设置随机且足够长的 `JWT_SECRET`；将三档 `LLM_*_MODEL`、`LLM_*_BASE_URL`、`LLM_*_API_KEY` 和 `EMBEDDING_*` 替换为实际可用的模型与服务。可在三档中使用同一兼容模型。示例模型名与 Key 仅为配置示意，不保证供应商可用性。聊天模型统一通过 OpenAI 兼容接口调用，不能直接填写 Anthropic 原生接口。

意图路由默认走 JEV（TypeSafe System One，非 OpenAI 兼容）：填写 `JEV_API_KEY`（或兼容命名的 `MAKERS_MODELS_KEY`）后启用；不填则自动降级为规则 + 轻量档模型。JEV 置信度低于 `JEV_LOW_CONFIDENCE_THRESHOLD`（默认 0.60）时，先走规则/轻量模型降级；降级仍不确定才弹出人工选择框。

自然语言“记录采购/报价”暂不支持；长期材料记录请通过上传供应商报价单并确认入库。

不配置真实模型时可运行注册、登录和数据库业务；对话、解析、AI 建议及向量知识库功能需要对应服务。知识库初始为空，需要自行上传资料；不会附带现有业务数据。

```powershell
cd backend
New-Item -ItemType Directory -Force data/uploads, chroma
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

另开一个终端启动前端：

```powershell
cd frontend
npm ci
npm run dev
```

浏览器访问 <http://localhost:5173>；接口文档 <http://localhost:8000/api/docs>；健康检查 <http://localhost:8000/api/health>。前端开发服务器已将 `/api` 代理到后端 8000 端口。首次使用在登录页注册管理员并创建团队，再邀请采购员。

Linux/macOS 对应激活命令为 `source .venv/bin/activate`，复制配置使用 `cp .env.example backend/.env`，创建目录使用 `mkdir -p data/uploads chroma`。

## 验证

```sh
cd backend
python -m pytest tests/ -v --cov=app --cov-report=term-missing
cd ../frontend
npm test
npm run build
```

后端单元/集成测试使用独立数据库与模型 Mock，不消耗真实模型配额。前端包含会话存储与 JWT 解析回归测试。GitHub Actions 执行后端测试、前端测试和构建。

2026-10-15 发布验证的具体结果见 `docs/release-verification.md`。真实模型回答质量、外部模型服务可用性与部署环境容量须在配置服务后另行验收。

## 目录

```text
backend/app/         API、Agent、Service、Schema、数据库与文件存储
backend/alembic/     数据库版本迁移
backend/tests/       后端测试
frontend/src/        页面、组件、接口层、状态管理与前端测试
docs/               需求、架构、模块 SDD 与发布验证
.github/workflows/  自动化验证
.env.example        不含真实密钥的配置模板
```

仓库以干净源码快照发布，不携带开发过程历史，保留运行与验证所需文件。数据库、上传资料、向量库、密钥、日志、虚拟环境、node_modules、构建产物、本地代理配置以及评测/压测数据和报告不随源码上传。开发约束见 `CLAUDE.md` 和 `AGENTS.md`。
