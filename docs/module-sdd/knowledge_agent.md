# SDD — 知识库检索 Agent（knowledge_agent）

> **依据**：system-design.md §2.2.5，PRD §FR-6，PRD §FR-8（斜杠命令）
> **代码位置**：`backend/app/agents/knowledge.py`
> **模型档位**：中量档（理解检索结果并组织语言）

---

## 1. 功能描述

处理行业知识库检索：
1. **查询**（知识库检索页面）：RAG 检索行业认知库，生成严格依据行业文档的回答。
2. **记录**（`/记录`、`/save`）：从当前会话上下文中提取关键业务信息，经用户确认后写入长期记忆库。

记录流程强制人工确认，不擅自写入（PRD §4.5 异常流程）。

---

## 2. 接口签名

```python
from app.schemas.knowledge_agent import (
    KnowledgeQueryInput, KnowledgeQueryResult,
    KnowledgeRecordExtract, KnowledgeSaveInput, KnowledgeSaveResult
)

class KnowledgeAgent:

    @staticmethod
    async def query(
        data: KnowledgeQueryInput,
        session_id: str,
        team_id: int,
        db: AsyncSession,
        chroma_client,
    ) -> KnowledgeQueryResult:
        """行业知识库 RAG 检索 + 回答。
        1. 只调用 KnowledgeBaseManager.search_industry()
        2. 拼接上下文（按 tech-stack.md §7.6 顺序）
        3. 调用中量档 LLM 生成回答（流式，yield token）
        4. 记录 LLMCallLogger.log()
        5. 若问题含"趋势"/"走势" → 额外返回 ECharts 折线图配置
        """

    @staticmethod
    async def extract_for_record(
        session_id: int,
        team_id: int,
        db: AsyncSession,
    ) -> KnowledgeRecordExtract:
        """/记录 命令第一步：从会话上下文提取候选信息，返回给前端供用户确认。
        若提取信息不足（缺少品种/规格/价格等必要字段）→ 返回反问文本，不返回 extract。
        """

    @staticmethod
    async def save_record(
        data: KnowledgeSaveInput,
        team_id: int,
        db: AsyncSession,
        chroma_client,
    ) -> KnowledgeSaveResult:
        """/记录 命令第二步：用户确认后，调用 KnowledgeBaseManager 写入长期记忆库。"""
```

### Pydantic 模型（`backend/app/schemas/knowledge_agent.py`）

```python
class KnowledgeQueryInput(BaseModel):
    question: str              # 用户问题
    session_id: str

class KnowledgeQueryResult(BaseModel):
    answer: str                # 自然语言回答
    sources: list[str]         # 引用来源类型
    trend_chart_option: dict | None  # ECharts 折线图，无趋势查询时为 None

class KnowledgeRecordExtract(BaseModel):
    needs_clarification: bool       # True 表示信息不足，返回反问文本
    clarification_text: str | None  # 信息不足时的反问
    extracted: dict | None          # 提取的候选信息（品种/规格/价格/供应商等）

class KnowledgeSaveInput(BaseModel):
    record_type: str           # "purchase" / "quote"
    data: dict                 # 用户在前端确认/修改后的数据

class KnowledgeSaveResult(BaseModel):
    success: bool
    message: str               # 如"已记录：香樟胸径12cm，单价 85元/株"
```

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `LLMFactory.get_medium()` | 生成回答 / 提取候选信息 |
| `LLMCallLogger.log()` | 成本记录 |
| `KnowledgeBaseManager.search_industry()` | 行业库检索 |
| `KnowledgeBaseManager.get_session_messages()` | 获取会话上下文（供提取） |
| `KnowledgeBaseManager.save_purchase_record()` / `save_quote_record()` | 写入长期记忆库 |

### Prompt 精简规范（query，约 100 token）

```
你是园林采购助手。根据知识库内容回答问题。
知识库：{{retrieved_content}}
要求：引用知识库内容，若不确定说"根据现有记录…"，不杜撰数字。
```

---

## 4. 异常处理

| 异常 | 触发条件 | 处理策略 |
|:---- |:-------- |:-------- |
| `LLMUnavailableError` | 中量档 LLM 不可用 | 只返回“模型整理失败，请核对下方检索依据”，同时保留原始检索依据；不生成泛化回答 |
| `SessionNotFoundError` | 提取时会话不存在 | HTTP 404 |
| 信息不足 | 会话中无足够业务信息可提取 | 返回 `needs_clarification=True` + 反问文本，不报错 |
