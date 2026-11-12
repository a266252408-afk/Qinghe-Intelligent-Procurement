# SDD — 知识库管理服务（knowledge_base_manager）

> **依据**：system-design.md §2.2.7，tech-stack.md §6，PRD §FR-7，PRD §6.1
> **代码位置**：`backend/app/services/knowledge_base.py`

---

## 1. 功能描述

管理三层知识库：行业认知库（事实）、长期记忆库（业务数据）、短期对话记忆库（会话）。

| 层 | 存储 | 权限 |
|:-- |:---- |:---- |
| 行业认知库 | SQLite `industry_knowledge` 分块索引 + Chroma（语义权重 0.7） | 团队只读，主管可维护 |
| 长期记忆库 | `material_history_records` + Chroma（向量化拼接文本） | 团队内共享，团队间隔离 |
| 短期对话记忆库 | SQLite `messages`/`conversation_sessions` | 用户私有（会话级）|

长期记忆库仅从供应商报价文件确认流程写入，不再从对话提取。每条报价明细保存供应商、材料、规格、供应商报价、成交价、报价日期、原始文件及上传/确认操作人；结构化记录写入 SQLite，检索文本同步写入 Chroma。完全相同的业务字段在同一团队内去重。

---

## 2. 接口签名

```python
from app.schemas.knowledge import (
    IndustryDocUploadResult, SearchResult, HistorySearchResult,
    PurchaseRecordCreate, QuoteRecordCreate,
    SessionCreate, SessionOut, MessageOut
)

class KnowledgeBaseManager:

    # ── 行业认知库 ─────────────────────────────────────────────
    @staticmethod
    async def upload_industry_doc(
        file_path: str,           # 本地存储路径（由 StorageInterface 返回）
        team_id: int,
        db: AsyncSession,
        chroma_client,            # Chroma 客户端（由依赖注入）
    ) -> IndustryDocUploadResult:
        """清洗并递归切分文件，向量化写入 Chroma，写入分块 SQLite 索引。"""

    @staticmethod
    async def search_industry(
        query: str,
        team_id: int,
        top_k: int = 5,
        db: AsyncSession = ...,
        chroma_client = ...,
    ) -> list[SearchResult]:
        """混合检索（BM25 0.3 + 向量 0.7），返回 Top-K 结果。"""

    # ── 长期记忆库 ─────────────────────────────────────────────
    @staticmethod
    async def index_material_record(record) -> str:
        """将已确认的材料历史记录写入 Chroma；SQLite 是精确查询主数据。"""

    @staticmethod
    async def search_history(
        query: str,               # 支持自然语言，如"去年买过香樟12cm吗"
        team_id: int,
        top_k: int = 5,
        db: AsyncSession = ...,
        chroma_client = ...,
    ) -> list[HistorySearchResult]:
        """混合检索长期记忆库（BM25 0.5 + 向量 0.5），返回历史记录。"""

    # ── 短期对话记忆库 ─────────────────────────────────────────
    @staticmethod
    async def create_session(
        user_id: int,
        project_id: int | None,   # 可关联项目
        title: str,
        db: AsyncSession,
    ) -> SessionOut:
        """创建新会话。"""

    @staticmethod
    async def get_session_messages(
        session_id: int,
        user_id: int,             # 防越权：会话属于该用户
        db: AsyncSession,
    ) -> list[MessageOut]:
        """按时间升序返回会话全部消息。"""

    @staticmethod
    async def add_message(
        session_id: int,
        role: str,                # "user" / "assistant"
        content: str,
        db: AsyncSession,
    ) -> None:
        """向会话追加一条消息。"""
```

### Pydantic 模型（`backend/app/schemas/knowledge.py`）

```python
class PurchaseRecordCreate(BaseModel):
    team_id: int
    order_id: int
    species: str               # 品种
    spec: str                  # 规格
    quantity: float
    unit: str
    project_name: str
    purchase_date: date

class QuoteRecordCreate(BaseModel):
    team_id: int
    order_id: int
    supplier_name: str
    species: str
    spec: str
    unit_price: float
    final_price: float | None  # 成交价，比价后确认
    delivery_days: int | None
    payment_terms: str | None
    quote_date: date

class SearchResult(BaseModel):
    source: str                # "industry" / "history"
    content: str               # 检索命中的文本片段
    score: float               # 相关度分数
    source_file: str | None    # 行业知识来源文件名

class HistorySearchResult(BaseModel):
    record_type: str           # "purchase" / "quote"
    species: str
    spec: str
    price: float | None
    supplier: str | None
    date: date | None
    score: float

class SessionCreate(BaseModel):
    project_id: int | None
    title: str

class SessionOut(BaseModel):
    session_id: int
    user_id: int
    project_id: int | None
    title: str
    created_at: datetime

class MessageOut(BaseModel):
    message_id: int
    session_id: int
    role: str
    content: str
    created_at: datetime
```

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `chromadb` | 向量存储与检索 |
| `rank_bm25` + `jieba` | BM25 关键词检索 + 中文分词 |
| `LangChain EnsembleRetriever` | 加权融合 BM25 + 向量结果 |
| `app.services.llm_factory.LLMFactory.get_embedding()` | 文档向量化 |
| `SQLAlchemy AsyncSession` | 业务数据 CRUD |
| `aiofiles` | 异步读取上传文件 |
| `app.core.exceptions` | SessionNotFoundError, KnowledgeDocError |

---

## 4. 异常处理

| 异常类 | 触发条件 | HTTP 状态码 |
|:------- |:-------- |:----------- |
| `KnowledgeDocError` | 文件解析失败（格式损坏/不支持） | 422 |
| `SessionNotFoundError` | session_id 不存在或不属于该用户 | 404 |
| `PermissionError` | 非 owner 尝试上传行业认知库文件 | 403 |

Chroma 写入失败：记录 warning + 抛出 `KnowledgeDocError`，不静默吞掉（不同于 llm_logger，知识库写失败需告知用户）。
