# SDD — 行业知识问答分发（chat_knowledge）

> **代码位置**：`backend/app/agents/chat_knowledge.py`
> **定位**：对话命令 `/知识` 的分发与结果帧组装，不包含检索与生成逻辑。

---

## 1. 功能描述

把聊天输入中的 `/知识`、`/knowledge` 命令剥离，调用 `KnowledgeAgent` 检索行业知识库，
并把结果整理成两部分：`answer` 进入对话流，`frame` 进入前端结果抽屉。

本模块不直接访问数据库、不调用大模型；检索与生成全部由 `KnowledgeAgent` 完成，
保持"分发层只做协议转换"的单一职责。

---

## 2. 接口签名

```python
class KnowledgeAnswer(BaseModel):
    answer: str     # 进入对话流的回答文本
    frame: dict     # 进入结果抽屉的来源与命中结果

def strip_knowledge_command(message: str) -> str:
    """去掉 /知识 或 /knowledge 前缀，保留实际问题。"""

async def answer_knowledge_question(
    question: str,      # 原始输入，可能带 /知识 前缀
    session_id: str,    # 当前对话会话 ID，供检索上下文使用
    team_id: int,       # 团队隔离标识
    db: AsyncSession,   # 数据库会话，供 KnowledgeAgent 记录调用日志
) -> KnowledgeAnswer: ...
```

### 空问题

仅输入 `/知识` 或 `/knowledge` 时不触发检索，返回固定提示与空帧：

```python
_EMPTY_HINT = "请在 /知识 后写明要查询的问题，例如：/知识 香樟树苗怎么养护。"
```

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `app.agents.knowledge.KnowledgeAgent.query` | 混合检索 + 大模型回答 |
| `app.schemas.knowledge_agent.KnowledgeQueryInput` | 检索请求模型（question / session_id） |
| `AsyncSession` | 交给 KnowledgeAgent 记录调用日志 |

---

## 4. 异常处理

- 知识库为空或检索无结果：由 `KnowledgeAgent` 返回带来源的空结果，本模块不另行处理。
- 空问题：直接返回提示文案与空 frame，不产生检索与模型调用。
- 大模型或嵌入接口异常：由 `KnowledgeAgent` 的降级链处理，本模块不捕获，避免重复兜底。
