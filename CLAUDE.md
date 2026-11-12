# CLAUDE.md — 园林工程智能采购助手 项目宪法

> 本文件是项目级规范，团队所有成员共享，提交到 Git。新成员克隆后 `claude` 启动即可获得一致上下文。
> 通过 `@AGENTS.md` 导入 Agent 角色定义。

---

## 1. 项目概述

面向园林工程采购场景的 AI 副驾驶式 Web 应用，通过对话式交互帮助采购员完成清单解析、询价单生成、报价比价、历史价格检索。定位"采购员的 AI 超级助手"，AI 辅助而非替代。

详细需求见 `docs/PRD.md`，技术选型见 `docs/tech-stack.md`，系统架构见 `docs/system-design.md`。

---

## 2. 技术栈

- **后端**：Python 3.11 + FastAPI + Pydantic v2 + SQLAlchemy 2.0（异步）+ SQLite
- **前端**：Vue 3 + Vite + Pinia + Axios + Element Plus + ECharts + markdown-it
- **大模型**：LangChain + OpenAI 兼容接口（三档分工：轻量/中量/重量）
- **知识库**：Chroma（向量）+ rank_bm25（关键词）+ LangChain EnsembleRetriever（混合检索）
- **认证**：python-jose（JWT）+ bcrypt
- **部署**：本地/云服务器直接运行（uvicorn + Vite 构建产物）
- **CI/CD**：GitHub Actions
- **测试**：pytest（后端）+ Vitest（前端）

详细选型理由见 `docs/tech-stack.md`。

---

## 3. 目录结构约定

```
园林工程智能采购助手/
├── CLAUDE.md                   # 本文件（项目宪法）
├── AGENTS.md                   # Agent 角色定义（由本文件导入）
├── docs/                       # 所有 SDD 设计文档
│   ├── PRD.md                  # 产品需求
│   ├── tech-stack.md           # 技术选型
│   ├── system-design.md        # 系统架构
│   ├── dev-log.md              # 施工日志
│   ├── module-sdd/             # 模块级 SDD
│   └── schemas/                # Pydantic Schema
├── backend/                    # 后端代码
│   ├── app/
│   │   ├── main.py             # FastAPI 入口
│   │   ├── core/               # 配置/安全/异常
│   │   ├── api/                # 路由层（不写业务）
│   │   ├── agents/             # Agent 实现（调用大模型）
│   │   ├── services/           # 业务逻辑（不调用大模型）
│   │   ├── models/             # SQLAlchemy 数据模型
│   │   ├── schemas/            # Pydantic 请求/响应 Schema
│   │   ├── storage/            # 文件存储
│   │   └── db/                 # 数据库连接
│   ├── tests/                  # 后端测试
│   └── alembic/                # 数据库迁移
├── frontend/                   # 前端代码
│   └── src/
│       ├── views/              # 页面视图
│       ├── components/         # 组件
│       ├── api/                # API 调用层（禁止组件直接 fetch）
│       ├── stores/             # Pinia 状态
│       └── utils/              # 工具
├── data/                       # SQLite 数据库 + 上传文件
├── chroma/                     # Chroma 向量库
├── .env.example
└── .gitignore
```

### 层级职责硬规则

| 层 | 职责 | 禁止 |
|:--- |:----- |:----- |
| `api/` | 路由、参数校验、调用 service | 写业务逻辑、直接调用大模型 |
| `agents/` | 调用大模型、工具调度 | 直接操作数据库（通过 service） |
| `services/` | 业务逻辑、数据 CRUD | 调用大模型 |
| `models/` | 数据表定义 | 写业务逻辑 |
| `schemas/` | 请求/响应数据结构 | 写业务逻辑 |

---

## 4. 编码规范

### 4.1 Python（后端）

- 遵循 PEP8，使用 ruff 格式化（行宽 120）。
- 使用 type hints（强制）。
- 函数不超过 50 行；超过则拆分。
- 模块间通信使用 Pydantic 模型，禁止裸 dict 传递。
- 异步优先：所有 I/O 操作（数据库、大模型、文件）用 async/await。
- 中文注释与文档字符串；**参数出现时需在注释中说明其作用**（用户偏好）。
- 自定义异常类，统一在 `core/exceptions.py`，API 层捕获。

### 4.2 JavaScript/TypeScript（前端）

- Prettier + ESLint 格式化（单引号、尾随逗号）。
- 组件不允许直接 `fetch`，必须通过 `src/api/` 调用。
- API 调用层统一返回 Promise，错误统一处理。
- 中文注释。

### 4.3 SQL 与数据库

- 所有业务表必须含 `team_id` 或其父实体含 `team_id`。
- 查询必须带 `team_id` 过滤，由数据访问层强制拦截。
- 禁止业务层裸 SQL 字符串拼接（用 SQLAlchemy 参数化）。
- 迁移必须用 Alembic，禁止手动改表结构。

---

## 5. 工作流（SDD 驱动）

### 5.1 开发流程

1. **先写 SDD 文档**：任何功能开发前，必须有对应的模块级 SDD（`docs/module-sdd/`）。
2. **骨架先行**：先定接口签名 + docstring，确认后再补业务逻辑。
3. **测试先行**：每实现一个模块，立即跑对应测试。
4. **对照 SDD 验收**：代码写完后对照 SDD 逐条验收。
5. **更新施工日志**：每完成一个模块，更新 `docs/dev-log.md`。

### 5.2 模块级 SDD 四要素

每个 `docs/module-sdd/<module>.md` 必须包含：
1. **功能描述**：做什么。
2. **接口签名**：核心方法签名 + 输入输出 Pydantic 模型。
3. **外部依赖**：依赖哪些模块/库/大模型。
4. **异常处理**：可能的异常与降级策略。

### 5.3 多 Agent 协作开发

复杂任务可拆分给多个 Agent 并行：
- 一个 Agent 负责一个模块的骨架。
- 接口契约（Schema）先定义，再并行实现。
- 实现完成后统一集成测试。

---

## 6. 大模型调用策略（成本优化核心约束）

### 6.1 三档模型分工

| 档位 | 环境变量前缀 | 适用任务 |
|:----- |:----- |:----- |
| 轻量 | `LLM_LIGHT_*` | 清单/报价解析、路由分类、摘要压缩 |
| 中量 | `LLM_MEDIUM_*` | 对话、知识库检索回答、趋势分析 |
| 重量 | `LLM_HEAVY_*` | 比价建议、复杂推理 |

> JEV（TypeSafe System One）是类型化判定服务，不属于三档聊天模型，不兼容 OpenAI
> `/chat/completions`。它同样必须通过 `LLMFactory.get_jev()` 获取并记录
> `LLMCallLogger`；调用失败时由 RouterAgent 静默降级到规则 + 轻量档。

### 6.2 调用原则

- **能不调用大模型就不调用**：纯数据库 CRUD、状态机、权限校验用确定性代码。
- **按复杂度选档**：简单提取用轻量档，推理用重量档。
- **通过 LLMFactory 获取实例**：禁止直接 new LLM/JEV 客户端，必须用工厂（带缓存）。
- **每次调用必须记录日志**：`LLMCallLogger.log()`，用于成本可观测。

### 6.3 上下文优化

- **Prompt 精简**：角色简短、规则用编号、示例最少、格式用 schema。
- **拼接顺序**：不易变的放上面（System/知识库）、易变的放尾部（当前输入）。
- **压缩阈值**：窗口接近模型上下文上限 70% 再触发，避免破坏 Prompt Cache。
- **压缩用轻量模型**：摘要任务不消耗中量/重量档配额。
- **检索结果裁剪**：RAG Top-20 但只喂 Top-5 给大模型。

### 6.4 缓存策略

- **Prompt Cache**：系统指令、知识库文档标记 cache=True。
- **本地缓存**：知识库查询类命中 SQLite 缓存，对话类不缓存。

---

## 7. 禁止事项（红线）

- **禁止**：跳过 SDD 直接写代码。
- **禁止**：在业务逻辑中硬编码 API Key（必须从环境变量读取）。
- **禁止**：删除或绕过测试代码。
- **禁止**：提交 .env 文件到 Git。
- **禁止**：前端组件直接调用大模型 API，必须经过后端 Agent。
- **禁止**：业务层裸 SQL 绕过 team_id 过滤。
- **禁止**：API 层直接调用大模型，必须通过 Agent。
- **禁止**：Agent 直接操作数据库，必须通过 Service。
- **禁止**：在未告知的情况下引入新的外部依赖。
- **必须**：修改函数签名时，同步更新所有调用方。
- **必须**：所有 API 返回统一格式 `{"code": 0, "msg": "ok", "data": {...}}`。

---

## 8. 测试要求

### 8.1 后端

- 框架：pytest + pytest-asyncio + pytest-cov
- 每个 Agent 必须有对应 `tests/test_<agent>.py`
- 每个 Service 必须有对应 `tests/test_<service>.py`
- 覆盖率：核心模块（agents/services）100%，整体 ≥ 80%
- 命令：`pytest tests/ -v --cov=app --cov-report=term-missing`

### 8.2 前端

- 框架：Vitest + Vue Test Utils
- 组件测试：`<component>.test.ts`
- 命令：`cd frontend && npm test -- --coverage`

### 8.3 大模型 Mock

- 测试中不调用真实大模型 API，用 Mock 对象。
- Mock 对象返回预定义的 Pydantic 模型实例。

---

## 9. 构建与执行命令

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
pytest tests/ -v
ruff check . && ruff format .
alembic upgrade head

# 前端
cd frontend
npm install
npm run dev
npm test
```

---

## 10. 提交规范

- 使用 Conventional Commits
- 格式：`<type>(<scope>): <description>`
- type：`feat` / `fix` / `refactor` / `docs` / `style` / `test` / `chore` / `perf`
- scope：`backend` / `frontend` / `docs` / `config` / `agent` / `service`
- 示例：
  - `feat(agent): add list parser agent with structured output`
  - `fix(service): correct team_id filter in order service`
  - `docs(prd): update acceptance criteria for compare feature`

---

## 11. 已知坑与注意事项

- SQLite 不支持并发写，生产环境需考虑连接池或改用 PostgreSQL。
- Chroma 嵌入式模式下数据存在 `chroma/` 目录，部署时需持久化保留该目录。
- LangChain 版本更新频繁，依赖需锁定版本号（`requirements.txt` 用 `==`）。
- SSE 在反向代理时需配置 `proxy_buffering off`，否则流式不生效。
- 中文字符在 BM25 分词时需配合 jieba，否则分词效果差。

---

## 12. 子代理模型选择

- **简单任务**（文件搜索、代码定位、文档阅读、grep/glob 探索）：子代理使用 `claude-haiku-4-5`。
- **复杂任务**（业务逻辑实现、SDD 编写、架构分析、代码 review）：由主代理（Sonnet）直接执行，不走子代理；若必须用子代理，指定 `claude-sonnet-4-6`。

---

## 13. 导入 AGENTS.md

@AGENTS.md
