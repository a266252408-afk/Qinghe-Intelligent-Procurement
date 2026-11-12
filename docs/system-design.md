# 系统架构设计 — 园林工程智能采购助手

> **文档定位**：基于 `docs/PRD.md`（需求）与 `docs/tech-stack.md`（技术选型），定义系统架构、模块划分、依赖关系、数据流与接口契约。是 `docs/module-sdd/`（模块级 SDD）与代码生成的依据。
> **版本**：v1.0

---

## 1. 架构总览

### 1.1 架构风格

**前后端分离 + 主+子 Agent 架构 + 三层知识库 + 混合检索**

- **前后端分离**：FastAPI（后端）+ Vue3（前端），通过 RESTful API + SSE 通信。
- **主+子 Agent**：主控 Router 识别意图并路由，5 个子 Agent 各司其职，分模型调用、上下文隔离。
- **三层知识库**：行业认知库（事实）+ 长期记忆库（业务数据）+ 短期对话记忆库（会话）。
- **混合检索**：BM25 + Chroma 向量 + EnsembleRetriever 加权融合 + BGE-Reranker 预留。

### 1.2 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│  前端层 (Vue3 + Vite + Pinia + Element Plus + ECharts)        │
│  ├─ 对话界面 (SSE 流式渲染)                                    │
│  ├─ 业务视图 (采购单/项目/审批/比价/知识库)                     │
│  └─ API 调用层 (Axios + fetch SSE)                             │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTP (RESTful + SSE)
┌───────────────────────▼─────────────────────────────────────┐
│  API 层 (FastAPI 路由)                                         │
│  ├─ 认证依赖 (JWT 校验)                                        │
│  ├─ 业务路由 (projects/orders/quotes/...)                      │
│  └─ 对话路由 (SSE 流式)                                        │
└───────────────────────┬─────────────────────────────────────┘
                        │ 函数调用 (Pydantic 模型)
┌───────────────────────▼─────────────────────────────────────┐
│  业务逻辑层 (Service)                                         │
│  ├─ 主控 Router Agent (意图识别 → 路由)                         │
│  ├─ 子 Agent 群 (清单/询价/比价/知识库/对话)                     │
│  ├─ 知识库管理 (三层)                                          │
│  ├─ 项目与采购单管理                                           │
│  ├─ 审批流                                                     │
│  └─ 认证与权限                                                 │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
┌───────▼───────┐ ┌─────▼───────┐ ┌─────▼─────────┐
│  数据访问层    │ │ 大模型集成层 │ │  文件存储层   │
│  (SQLAlchemy  │ │ (LangChain) │ │  (Storage     │
│   异步)       │ │              │ │   接口)       │
└───────┬───────┘ └─────┬───────┘ └─────┬─────────┘
        │               │               │
┌───────▼───────┐ ┌─────▼──────────┐ ┌──▼──────────┐
│  SQLite       │ │  OpenAI 兼容   │ │  本地文件系统│
│  (WAL 模式)   │ │  (三档模型)    │ │              │
└───────────────┘ └────────────────┘ └─────────────┘
        │
┌───────▼───────┐ ┌──────────────┐
│  Chroma       │ │ rank_bm25    │
│  (向量库)     │ │ (BM25 索引)  │
└───────────────┘ └──────────────┘
```

### 1.3 核心设计原则

1. **单一职责**：每个模块/Agent 只做一件事，不跨层。
2. **开闭原则**：工具/Agent 新增只需注册，不改现有代码。
3. **AI 辅助而非替代**：大模型做识别/提取/建议，人做确认/决策。
4. **成本可控**：三档模型分工、上下文压缩、缓存复用。
5. **团队隔离**：数据访问层强制 `team_id` 过滤。
6. **骨架先行**：先定接口与签名，后补业务逻辑。

---

## 2. 模块划分

### 2.1 模块总览

| 模块 | 类型 | 职责 | 关键依赖 |
|:----- |:----- |:----- |:----- |
| Router Agent | Agent | 意图识别 → 路由到子 Agent | 轻量档 LLM |
| 清单解析 Agent | Agent | 文件/文本 → 结构化采购清单 | 轻量档 LLM、文件读取 |
| 询价单 Agent | Agent | 采购清单 + 模板 → 询价单文件 | 轻量档 LLM、模板引擎 |
| 比价 Agent | Agent | 多报价 + 历史评分 → 比价报告 + 建议 | 重量档 LLM、比价计算 |
| 知识库 Agent | Agent | 用户问题 + 检索结果 → 自然语言回答 | 中量档 LLM、EnsembleRetriever |
| 对话 Agent | Agent | 用户消息 + 对话历史 → 流式回复 | 中量档 LLM、Memory |
| 知识库管理 | Service | 三层知识库 CRUD + 向量化 + 检索 | Chroma、rank_bm25、SQLAlchemy |
| 项目采购单管理 | Service | 项目/采购单/状态机 | SQLAlchemy |
| 审批流 | Service | 审批记录、状态流转 | SQLAlchemy |
| 认证与权限 | Service | 登录/JWT/团队隔离 | python-jose、bcrypt |
| 文件存储 | Service | 上传/下载/路径管理 | Storage 接口 |
| 成本可观测 | Service | LLM 调用日志记录与查询 | SQLAlchemy |
| LLM 工厂 | Infra | 按档位创建 LLM 实例（缓存） | LangChain |
| API 响应桥接 | Infra | 统一响应格式 + 异常捕获 | Pydantic |

### 2.2 模块详细定义

#### 2.2.1 主控调度模块（Router Agent）

**职责**：接收用户输入 → 识别意图 → 路由到对应子 Agent。

**核心方法**：
```python
class RouterAgent:
    async def route(self, data: RouterInput, team_id: int, db: AsyncSession) -> RouteResult:
        """JEV 主路由；失败时降级规则 + 轻量模型，返回 intent/target_agent/confidence"""
```

**路由规则**：
- **JEV 优先**：所有消息（含附件、斜杠命令、历史价格语义）先由 JEV 判定 6 类意图；
- JEV `confidence < 0.60` 或调用失败 → 先降级规则 + 轻量模型；降级仍低置信度
  才由 ChatAgent 触发人工确认弹窗；
- JEV 超时/429/5xx/协议错误 → 静默降级：
  - 附件类型 → 清单/报价解析；
  - 斜杠命令 → 询价/比价/历史/记录；
  - 历史价格关键词 → 对话 Agent（长期材料工具）；
  - 仍无法判定 → 轻量档 LLM；
- 规则层不再前置短路，只在 JEV 故障时启用。

**不负责**：具体业务逻辑，只做意图分类与路由。

#### 2.2.2 清单解析 Agent

**职责**：从文件/文本提取结构化采购清单。

**核心方法**：
```python
class ListParserAgent:
    async def parse(self, input: ParseInput) -> ParseResult:
        """解析输入为 PurchaseList"""
        # input: file_path 或 text
        # output: PurchaseList Pydantic 对象 + confidence
```

**工具**：文件读取（Excel/CSV 用 openpyxl，文本直接读）。

**模型**：轻量档。

#### 2.2.3 询价单生成 Agent

**职责**：基于采购清单生成询价单文件。

**核心方法**：
```python
class InquiryAgent:
    async def generate(self, order_id: int, template_id: str) -> InquiryResult:
        """生成询价单文件"""
        # output: file_path + 预览数据
```

**工具**：模板引擎（openpyxl 填充 Excel 模板）。

**模型**：轻量档（仅填充，非生成）。

#### 2.2.4 比价分析 Agent

**职责**：多报价对比 + 历史评分 + AI 建议。

**核心方法**：
```python
class CompareAgent:
    async def compare(self, order_id: int) -> CompareResult:
        """生成比价报告"""
        # output: 表格数据 + 图表配置 + AI 建议文本
```

**工具**：比价计算（确定性代码，权重可配置）。

**模型**：重量档（多维度推理）。

#### 2.2.5 知识库检索 Agent

**职责**：检索行业认知库与长期记忆库，生成自然语言回答。

**核心方法**：
```python
class KnowledgeAgent:
    async def query(self, question: str, session_id: str) -> QueryResult:
        """RAG 检索 + 回答"""
        # 调用 EnsembleRetriever (BM25 + Chroma)
        # 喂给大模型生成回答

    async def save_record(self, session_id: str, data: KnowledgeRecordCreate) -> SaveResult:
        """斜杠命令 /记录 触发，提取并确认入库。data 为 Pydantic 模型，具体类型在 SDD 中定义"""
```

**工具**：EnsembleRetriever（BM25 + Chroma 向量）。

**模型**：中量档。

#### 2.2.6 对话 Agent

**职责**：日常对话、流式回复。

**核心方法**：
```python
class ChatAgent:
    async def chat_stream(self, message: str, session_id: str) -> AsyncGenerator:
        """流式对话，yield 每个 token"""
```

**工具**：Memory（ConversationSummaryBufferMemory）。

**模型**：中量档。

#### 2.2.7 知识库管理模块

**职责**：三层知识库的 CRUD、向量化、检索。

**核心方法**：
```python
class KnowledgeBaseManager:
    # 行业认知库
    async def upload_industry_doc(self, file_path: str, team_id: int) -> None: ...
    async def search_industry(self, query: str, team_id: int, top_k: int = 5) -> list: ...

    # 长期记忆库（record 参数均为 Pydantic 模型，禁止裸 dict，具体类型在各模块 SDD 中定义）
    async def save_purchase_record(self, record: PurchaseRecordCreate) -> None: ...
    async def save_quote_record(self, record: QuoteRecordCreate) -> None: ...
    async def search_history(self, query: str, team_id: int, top_k: int = 5) -> list[HistorySearchResult]: ...

    # 短期对话记忆库
    async def create_session(self, user_id: int, project_id: int) -> int: ...
    async def get_session_messages(self, session_id: int) -> list: ...
    async def add_message(self, session_id: int, role: str, content: str) -> None: ...
```

**依赖**：Chroma、rank_bm25、SQLAlchemy。

**三层知识库存储映射（统一存储，非每层独立数据库）**：

三层知识库共享同一套底层存储，按 collection/实体表 + 权限层级 + 检索权重区分，不各自建库：

| 知识库层 | 结构化数据（SQLite/WAL） | 向量（Chroma） | 关键词（rank_bm25） | 原始文件（本地存储） | 权限 |
|:--- |:--- |:--- |:--- |:--- |:--- |
| 行业认知库 | `industry_knowledge` 表（含 `vector_id`） | 语义为主，权重 0.7 | 兜底 | 上传的 PDF/Word/Excel/文本 | 团队只读，主管可维护 |
| 长期记忆库 | 采购/报价/成交/供应商业务表 | 权重 0.5（**需拼文本向量化**，见下） | 权重 0.5（规格精确匹配） | 历史 Excel 解析入库 | 团队内共享，团队间隔离 |
| 短期对话记忆库 | `messages`/`session` 表 | 不向量化 | — | — | 用户私有（会话级） |

> **长期记忆库向量化要点**：FR-6 支持自然语言查询（如"去年买过香樟12cm吗"），BM25 只能做精确规格匹配，口语化语义查询接不住。写入长期记录（清单/报价/成交/供应商）时，须把结构化记录拼成一段可检索文本（品种 + 规格 + 数量 + 单价 + 日期 + 供应商 + 项目），一并写入 Chroma，语义检索才能命中。

> **短期对话记忆库不向量化**：会话级、用户私有，靠对话上下文窗口 + 轻量摘要压缩维护；进向量库只会引入数据噪声、加剧团队隔离复杂度，保持仅存 SQLite。

> **统一存储收益**：一套 SQLite 便于 team_id 隔离、事务与 Alembic 迁移统一管理；Chroma 一个实例按 collection 分区；不出现跨库联查问题。

#### 2.2.8 项目与采购单管理

**职责**：项目/采购单/采购项的 CRUD + 状态机。

**核心方法**：
```python
class ProjectService:
    async def create_project(self, data: ProjectCreate) -> Project: ...
    async def list_projects(self, team_id: int) -> list[Project]: ...

class PurchaseOrderService:
    async def create_order(self, data: OrderCreate) -> PurchaseOrder: ...
    async def update_status(self, order_id: int, status: OrderStatus) -> None: ...
    async def submit_for_approval(self, order_id: int) -> None: ...
```

#### 2.2.9 审批流模块

**职责**：审批记录、状态流转。

**核心方法**：
```python
class ApprovalService:
    async def approve(self, order_id: int, approver_id: int) -> None: ...
    async def reject(self, order_id: int, approver_id: int, reason: str) -> None: ...
    async def list_pending(self, approver_id: int) -> list[ApprovalRecord]: ...
```

#### 2.2.10 认证与权限模块

**职责**：登录即注册、JWT、团队隔离。

**核心方法**：
```python
class AuthService:
    async def login_or_register(self, username: str, password: str) -> Token: ...
    async def verify_token(self, token: str) -> UserInfo: ...
    async def create_team(self, creator_id: int, name: str) -> Team: ...
    async def join_team(self, user_id: int, invite_code: str) -> None: ...
```

#### 2.2.11 文件存储模块

**职责**：文件上传/下载/路径管理，抽象 Storage 接口。

**核心方法**：
```python
class StorageInterface(ABC):
    @abstractmethod
    async def save(self, file: UploadFile, team_id: int, type: str) -> str: ...
    @abstractmethod
    async def read(self, path: str) -> bytes: ...
    @abstractmethod
    async def delete(self, path: str) -> None: ...

class LocalStorage(StorageInterface):
    # MVP 实现：本地文件系统
```

#### 2.2.12 成本可观测模块

**职责**：LLM 调用日志记录。

**核心方法**：
```python
class LLMCallLogger:
    async def log(self, agent_name: str, model: str, input_tokens: int,
                  output_tokens: int, cost: float, latency_ms: int,
                  cache_hit: bool, session_id: str) -> None: ...
    async def summary_by_model(self, days: int = 7) -> dict: ...
    async def summary_by_agent(self, days: int = 7) -> dict: ...
```

#### 2.2.13 LLM 工厂模块

**职责**：按档位创建 LLM 实例，带缓存。

> **Anthropic 适配说明**：LLMFactory 统一使用 LangChain 的 `ChatOpenAI`（指定 `base_url` 与 `api_key`）访问 OpenAI 兼容端点。Anthropic 提供兼容端点 `https://api.anthropic.com/v1`，可通过此方式调用；如遇工具调用/流式兼容性问题，可改用 `langchain_anthropic.ChatAnthropic`。具体适配逻辑在 `llm_factory.md` SDD 中明确。

**核心方法**：
```python
class LLMFactory:
    _instances: dict = {}  # 档位 → LLM 实例缓存

    @classmethod
    def get_light(cls) -> BaseChatModel:
        """轻量档 LLM"""
        if "light" not in cls._instances:
            cls._instances["light"] = create_llm(
                model=settings.LLM_LIGHT_MODEL,
                base_url=settings.LLM_LIGHT_BASE_URL,
                api_key=settings.LLM_LIGHT_API_KEY,
            )
        return cls._instances["light"]

    @classmethod
    def get_medium(cls) -> BaseChatModel: ...
    @classmethod
    def get_heavy(cls) -> BaseChatModel: ...
    @classmethod
    def get_embedding(cls) -> Embeddings: ...
```

#### 2.2.14 API 响应桥接模块

**职责**：统一响应格式 + 异常捕获。

**核心方法**：
```python
class APIResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: Any = None

# 异常处理中间件
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return APIResponse(code=500, msg=str(exc), data=None)
```

---

## 3. 模块依赖关系

### 3.1 依赖关系图

```
Frontend (Vue3)
    ↓ HTTP/SSE
API Layer (FastAPI)
    ↓
├─ AuthService ←──────────── 全局依赖（所有路由需认证）
├─ ProjectService ─────────→ PurchaseOrderService
├─ PurchaseOrderService ───→ ApprovalService
├─ ApprovalService
│
├─ /api/chat (SSE)
│   ↓
│  RouterAgent ──┬─→ ListParserAgent ──→ StorageInterface
│                ├─→ InquiryAgent ──→ StorageInterface
│                ├─→ CompareAgent ──→ PurchaseOrderService
│                ├─→ KnowledgeAgent ──→ KnowledgeBaseManager
│                └─→ ChatAgent ──→ KnowledgeBaseManager (Memory)
│
├─ /api/knowledge (文件上传)
│   ↓
│  KnowledgeBaseManager ──┬─→ Chroma (向量)
│                         ├─→ rank_bm25 (关键词)
│                         └─→ SQLAlchemy (业务数据)
│
└─ LLMCallLogger ←──── 所有 Agent 调用后记录

数据层：
├─ SQLAlchemy ──→ SQLite (WAL)
├─ Chroma (嵌入式)
└─ rank_bm25 (内存索引，启动时加载)
```

### 3.2 依赖规则

- **API 层不直接调用大模型**：必须通过 Agent 调用。
- **Agent 不直接操作数据库**：通过 Service 层。
- **Service 层不调用大模型**：纯业务逻辑用确定性代码。
- **所有数据查询必须带 team_id**：由 SQLAlchemy 事件监听器强制注入。

---

## 4. 数据流

### 4.1 正常流程：清单解析

```
1. 前端 POST /api/orders/{id}/upload-list (含文件)
2. API 层接收 → 校验 JWT → 提取 team_id
3. PurchaseOrderService.save_file() → StorageInterface.save()
4. RouterAgent.route() → 识别为 "parse_list"
5. ListParserAgent.parse(file_path)
   - 读取文件 (openpyxl)
   - 调用轻量档 LLM with_structured_output(PurchaseList)
   - LLMCallLogger.log()
6. 返回 PurchaseList + confidence
7. 若 confidence < 0.8 → 标注不确定字段
8. 前端展示预览表格 → 用户确认/修正
9. POST /api/orders/{id}/items → PurchaseOrderService.save_items()
10. KnowledgeBaseManager.save_purchase_record() → 长期记忆库
```

### 4.2 正常流程：比价分析

```
1. 前端 POST /api/orders/{id}/compare
2. API 层 → PurchaseOrderService.get_quotes(order_id)
3. RouterAgent.route() → "compare"
4. CompareAgent.compare(order_id)
   - 获取所有报价 (QuoteService)
   - 获取历史评分 (KnowledgeBaseManager.search_history)
   - 比价计算（确定性代码，权重可配置）
   - 调用重量档 LLM 生成自然语言建议
   - LLMCallLogger.log()
5. 返回 CompareResult (表格 + 图表配置 + AI 建议)
6. 前端渲染表格 + ECharts 柱状图 + 雷达图 + 建议文本
```

### 4.3 正常流程：对话（SSE 流式）

```
1. 前端 POST /api/chat/stream (含 message + session_id)
2. API 层 → StreamingResponse (SSE)
3. RouterAgent.route(message) → JEV 判定意图；低置信度或失败时降级规则 + 轻量模型
4. 降级结果仍低置信度/失败 → SSE `type=route_confirm`，前端弹窗等待人工选择；
   用户选择后以 `pending_token + forced_intent` 复用 POST /api/chat 续跑
5. `knowledge_query` → KnowledgeAgent.query，答案进对话 + `type=knowledge` 来源帧
6. 其他意图 → ChatAgent.chat_stream(message, session_id)
   - 加载会话历史 (KnowledgeBaseManager.get_session_messages)
   - 拼接上下文（按顺序：System/知识库/检索/摘要/最近N轮/当前输入）
   - 调用中量档 LLM stream()
   - 每个 token yield 给前端
   - LLMCallLogger.log() (汇总)
7. 完成后 KnowledgeBaseManager.add_message() 保存对话
8. 若超出窗口阈值 → 触发摘要压缩（轻量档模型）
```

### 4.4 异常流程：大模型不可用

```
1. Agent 调用 LLM → 捕获 LLMException
2. 降级策略：
   - 清单解析：返回错误，提示用户手动录入
   - 比价：仍返回表格（确定性代码计算），AI 建议部分标注 "source: template"
   - 对话：返回固定话术 "服务暂时不可用，请稍后再试"
   - JEV 路由：静默降级到规则 + 轻量档 LLM，不向用户插入额外提示
3. LLMCallLogger.log() 记录失败
4. APIResponse 返回 code=503 + 降级数据
```

### 4.5 异常流程：斜杠命令意图不明确

```
1. 用户输入 "/记录" 但当前会话无关键信息
2. KnowledgeAgent 判断信息不足
3. AI 反问澄清："请问要记录什么？品种/规格/价格/供应商？"
4. 不擅自执行写入
```

---

---

## 5. 补充数据模型（对齐 tech-stack.md §7）

以下两张表在 PRD §6.2 核心实体中未列出，但施工时必须创建：

```sql
-- LLM 成本可观测（开发者侧，对应 LLMCallLogger，tech-stack.md §7.7）
llm_call_logs(id, agent_name, model, input_tokens, output_tokens, cost,
              latency_ms, cache_hit, session_id, created_at)

-- LLM 本地缓存（知识库查询类命中直接返回，tech-stack.md §7.5 策略D）
-- 缓存键 = (model + system_prompt_hash + user_input_hash)
llm_cache(id, prompt_hash, model, response, created_at)
```

> 注意：`llm_call_logs` 和 `llm_cache` 无 `team_id`，属于开发者运维表，不参与团队隔离过滤。

---

## 6. 接口契约（概要）

### 5.1 统一响应格式

```python
class APIResponse(BaseModel):
    code: int = 0          # 0 成功，非 0 失败
    msg: str = "ok"
    data: Any = None
```

### 5.2 核心 API 端点

#### 认证
```
POST /api/auth/login         # 登录即注册
POST /api/auth/teams         # 创建团队
POST /api/auth/teams/join    # 加入团队
GET  /api/auth/me            # 获取当前用户
```

#### 项目与采购单
```
GET  /api/projects                  # 项目列表
POST /api/projects                  # 创建项目
GET  /api/projects/{id}/orders      # 项目下采购单
POST /api/orders                    # 创建采购单
GET  /api/orders/{id}               # 采购单详情
PUT  /api/orders/{id}/status        # 更新状态
POST /api/orders/{id}/submit        # 提交审批
POST /api/orders/{id}/items         # 保存清单项
```

#### 清单解析
```
POST /api/orders/{id}/upload-list   # 上传清单文件
POST /api/parse/list                 # 直接文本解析
```

#### 询价单
```
POST /api/orders/{id}/inquiry       # 生成询价单
GET  /api/inquiry-templates          # 模板列表
```

#### 报价与比价
```
POST /api/orders/{id}/upload-quote  # 上传报价文件
POST /api/orders/{id}/compare       # 比价分析
```

#### 审批
```
GET  /api/approvals/pending         # 待审批列表
POST /api/approvals/{id}/approve    # 通过
POST /api/approvals/{id}/reject     # 驳回
```

#### 知识库
```
POST /api/knowledge/upload          # 上传知识库文件
GET  /api/knowledge/search          # 检索
POST /api/knowledge/record          # /记录 命令
```

#### 对话（SSE）
```
POST /api/chat/stream               # 流式对话
GET  /api/sessions                   # 会话列表
POST /api/sessions                   # 创建会话
```

### 5.3 详细 Schema

详细 Pydantic Schema 见 `docs/schemas/` 目录，每个模块一份。

---

## 7. 上下文拼接与成本优化（对齐 tech-stack.md 第7章）

### 6.1 上下文拼接顺序（所有 Agent 通用）

```
[1] SystemMessage：角色定义 + 规则 + 输出格式（固定，可缓存）
[2] SystemMessage：知识库文档（半静态，标记 cache=True）
[3] HumanMessage：检索结果（RAG Top-5）
[4] HumanMessage：对话历史摘要（按阈值压缩）
[5] 最近 N 轮原文（动态）
[6] HumanMessage：当前用户输入（最易变，放尾部）
```

### 6.2 成本控制要点

- **三档模型分工**：见 tech-stack.md 7.2。
- **压缩阈值**：窗口接近模型上下文上限 70% 再触发，避免破坏 Prompt Cache。
- **压缩用轻量模型**：摘要任务不消耗中量/重量档配额。
- **本地缓存**：知识库查询类命中直接返回。

---

## 8. 技术选型对齐

详细技术选型见 `docs/tech-stack.md`，本架构文档对齐如下关键点：

| 架构层次 | 选型 | 说明 |
|:----- |:----- |:----- |
| 后端框架 | FastAPI + Pydantic v2 | 异步、自动文档 |
| 数据库 | SQLite + SQLAlchemy 2.0 异步 | WAL 模式、Alembic 迁移 |
| 大模型集成 | LangChain | 主+子 Agent 架构基础 |
| 流式协议 | SSE | StreamingResponse |
| 向量库 | Chroma | 嵌入式 |
| 关键词检索 | rank_bm25 | BM25 |
| 混合检索 | LangChain EnsembleRetriever | RRF 融合 |
| 重排器 | BGE-Reranker（预留） | MVP 不启用 |
| JWT | python-jose | FastAPI 官方推荐 |
| 密码哈希 | bcrypt | 原生接口，无中间层兼容问题 |
| 部署 | 本地/云服务器直接运行 | 前后端分离部署 |

---

## 9. 目录结构

```
园林工程智能采购助手/
├── CLAUDE.md                   # 项目宪法
├── AGENTS.md                   # Agent 角色定义
├── docs/
│   ├── PRD.md                  # 产品需求
│   ├── tech-stack.md           # 技术选型
│   ├── system-design.md        # 系统架构（本文档）
│   ├── dev-log.md              # 施工日志
│   ├── module-sdd/             # 模块级 SDD
│   └── schemas/                # Pydantic Schema
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI 入口
│   │   ├── core/               # 配置、安全、异常
│   │   │   ├── config.py
│   │   │   ├── security.py     # JWT、密码哈希
│   │   │   └── exceptions.py
│   │   ├── api/                # 路由层
│   │   │   ├── auth.py
│   │   │   ├── projects.py
│   │   │   ├── orders.py
│   │   │   ├── approvals.py
│   │   │   ├── chat.py
│   │   │   └── knowledge.py
│   │   ├── agents/             # Agent 实现
│   │   │   ├── router.py
│   │   │   ├── list_parser.py
│   │   │   ├── inquiry.py
│   │   │   ├── compare.py
│   │   │   ├── knowledge.py
│   │   │   └── chat.py
│   │   ├── services/           # 业务逻辑
│   │   │   ├── auth_service.py
│   │   │   ├── project_service.py
│   │   │   ├── order_service.py
│   │   │   ├── approval_service.py
│   │   │   ├── knowledge_base.py
│   │   │   ├── llm_factory.py
│   │   │   └── llm_logger.py
│   │   ├── models/             # SQLAlchemy 模型
│   │   ├── schemas/            # Pydantic Schema
│   │   ├── storage/            # 文件存储
│   │   │   └── local_storage.py
│   │   └── db/                 # 数据库连接
│   ├── tests/                  # 后端测试
│   ├── alembic/                # 数据库迁移
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/              # 页面视图
│   │   ├── components/         # 组件
│   │   ├── api/                # API 调用层
│   │   ├── stores/             # Pinia 状态
│   │   └── utils/              # 工具
│   └── package.json
├── data/                       # SQLite + 上传文件
├── chroma/                     # Chroma 向量库
├── .env.example
└── .gitignore
```

---

## 10. 验收标准

- [x] 架构总览清晰展示分层与组件
- [x] 模块划分包含 14 个模块的职责与核心方法
- [x] 依赖关系图展示模块间调用
- [x] 正常流程（清单解析/比价/对话）与异常流程（大模型不可用）都有描述
- [x] 接口契约概要 + 目录结构已定义
- [x] 与 tech-stack.md 选型对齐

---

**文档结束。后续将基于本文档拆分模块级 SDD（docs/module-sdd/）与 Pydantic Schema（docs/schemas/）。**
