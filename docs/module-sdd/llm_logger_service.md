# SDD — LLM 日志服务（llm_logger_service）

> **依据**：system-design.md §2.2.12，tech-stack.md §7.7，CLAUDE.md §6.2
> **代码位置**：`backend/app/services/llm_logger.py`

---

## 1. 功能描述

记录每次 LLM 调用的详细信息到 `llm_call_logs` 表（成本可观测，开发者侧专用）。
提供按模型、按 Agent 的汇总查询，用于调优与成本监控。
写入失败不阻断主链路（仅 log warning，不抛出异常）。

---

## 2. 接口签名

```python
from app.schemas.llm_logger import LLMCallLogCreate, LLMCallSummary

class LLMCallLogger:

    @staticmethod
    async def log(
        agent_name: str,       # 调用方 Agent 名称，如 "list_parser"
        model: str,            # 实际使用的模型，如 "deepseek-v3"
        input_tokens: int,     # 输入 token 数
        output_tokens: int,    # 输出 token 数
        cost: float,           # 本次调用成本（元）
        latency_ms: int,       # 端到端耗时（毫秒）
        cache_hit: bool,       # 是否命中供应商 Prompt Cache
        session_id: str,       # 关联会话 ID（无会话时传 ""）
        db: AsyncSession,      # 数据库会话（由调用方注入）
    ) -> None:
        """写入 llm_call_logs 表；写入失败只记录 warning，不抛出。"""

    @staticmethod
    async def summary_by_model(
        days: int,             # 统计最近 N 天
        db: AsyncSession,      # 数据库会话
    ) -> list[LLMCallSummary]:
        """按模型汇总：model / total_calls / total_input_tokens / total_output_tokens / total_cost。"""

    @staticmethod
    async def summary_by_agent(
        days: int,             # 统计最近 N 天
        db: AsyncSession,      # 数据库会话
    ) -> list[LLMCallSummary]:
        """按 Agent 汇总：agent_name / total_calls / total_cost / avg_latency_ms。"""
```

### Pydantic 模型（`backend/app/schemas/llm_logger.py`）

```python
class LLMCallLogCreate(BaseModel):
    agent_name: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    latency_ms: int
    cache_hit: bool
    session_id: str

class LLMCallSummary(BaseModel):
    key: str           # model 名称或 agent_name
    total_calls: int
    total_cost: float
    avg_latency_ms: float
```

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `SQLAlchemy AsyncSession` | 写入 / 查询 `llm_call_logs` 表 |
| `app.models.llm_log.LLMCallLog` | ORM 模型 |
| Python `logging` | 写入失败时记录 warning |

---

## 4. 异常处理

| 异常 | 触发条件 | 处理策略 |
|:---- |:-------- |:-------- |
| DB 写入失败（任意异常） | 数据库不可用 / 锁超时 | `except Exception: logger.warning(...)` 吞掉，不抛出，不阻断 Agent 主链路 |
| 查询失败 | 同上 | 汇总接口返回空列表，不向上抛出 |
