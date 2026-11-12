# SDD — LLM 并发闸门（llm_gate）

> **代码位置**：`backend/app/services/llm_gate.py`
> **定位**：按模型档位限制进程内在途请求数，防止突发流量打爆供应商配额。
> **约束**：只做并发、超时与瞬时错误重试；不改变调用语义，不记录业务日志。

---

## 1. 功能描述

所有大模型、嵌入、重排与 JEV 调用都应经过 LLMGate：

- **流式调用**：`acquire(tier)` 只做信号量排队，不设总超时；
- **非流式调用**：`run(tier, op)` 在信号量内执行，带单次超时与网络类瞬时错误重试；
- 档位映射：`light` / `medium` / `heavy` / `embedding` / `rerank` / `jev`；
- 未知档位按 `medium` 兜底，避免调用方因拼写错误崩溃；
- 并发上限为 0 时使用足够大的信号量，保持同一代码路径（等于不限制）。

> 信号量是**进程内资源**：多 worker 部署时实际在途上限 = 配置值 × worker 数。

---

## 2. 接口签名

```python
class LLMGate:
    @classmethod
    @asynccontextmanager
    async def acquire(cls, tier: str) -> AsyncIterator[None]:
        """流式调用：仅并发排队，不设总超时。"""

    @classmethod
    async def run(
        cls,
        tier: str,
        op: Callable[[], Awaitable[T]],   # 零参异步工厂，每次重试重新调用
        *,
        attempts: int | None = None,      # 缺省取 settings.LLM_RETRY_ATTEMPTS
    ) -> T:
        """非流式调用：信号量 + 超时 + 网络类错误有限重试。"""

    @classmethod
    def timeout_s(cls, tier: str) -> float: ...
```

### 配置映射

| 档位 | 并发配置 | 超时配置 |
|:---- |:---- |:---- |
| light | `LLM_LIGHT_CONCURRENCY` | `LLM_LIGHT_TIMEOUT_S` |
| medium | `LLM_MEDIUM_CONCURRENCY` | `LLM_MEDIUM_TIMEOUT_S` |
| heavy | `LLM_HEAVY_CONCURRENCY` | `LLM_HEAVY_TIMEOUT_S` |
| embedding | `EMBEDDING_CONCURRENCY` | `EMBEDDING_TIMEOUT_S` |
| rerank | `RERANK_CONCURRENCY` | `RERANK_TIMEOUT_S` |
| jev | `JEV_CONCURRENCY` | `JEV_TIMEOUT_S` |

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `app.core.config.settings` | 各档位并发上限、超时、重试次数与退避 |
| `openai`（可选） | 识别 `APIConnectionError` / `APITimeoutError` / `RateLimitError` |
| 标准库 `asyncio` | 信号量、`wait_for`、退避 |

`openai` 不可用时不报错，仅按内置的 `asyncio.TimeoutError` / `ConnectionError` 判断重试。

---

## 4. 异常处理

- 非流式调用超时：`asyncio.wait_for` 抛 `TimeoutError`，属于可重试的网络类错误；
- 网络类瞬时错误：按 `backoff × 2^(n-1)` 退避重试，次数用尽后抛出最后一次异常；
- 业务异常（如供应商 400）：不重试，原样上抛；
- 未知档位：静默按 `medium` 处理，不抛异常；
- 流式调用不设总超时，避免长回答被截断；超时由供应商与上层协议控制。
