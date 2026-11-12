# SDD — 重排序客户端（rerank_client）

> **代码位置**：`backend/app/services/rerank_client.py`
> **接口**：Cohere 风格 `POST /rerank`（默认 SiliconFlow `BAAI/bge-reranker-v2-m3`）。

---

## 1. 功能描述

对混合检索召回的候选文档，按"查询-文档"语义相关度做二阶段精排，返回文档下标与分数。
只负责 HTTP 传输、限速重试与降级；不包含检索、截断或 Prompt 逻辑。

默认关闭（`RAG_RERANK_ENABLED=false`），需评测裁决后再开启；开启后由
`KnowledgeBaseManager` 在混合召回之后调用。

---

## 2. 接口签名

```python
class RerankClient:
    def __init__(
        self,
        model: str,          # 重排序模型名
        base_url: str,       # 服务根地址
        api_key: str,        # 为空时直接返回空结果
        timeout_s: float = 30.0,
    ) -> None: ...

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
        *,
        agent_name: str = "knowledge_rerank",  # 调用日志中的 Agent 名
        session=None,                          # 传入 AsyncSession 时记录调用日志
    ) -> list[tuple[int, float]]:
        """返回 [(文档下标, 相关度分)]，按分数降序；失败返回 []。"""
```

实例必须通过 `LLMFactory.get_rerank_client()` 获取（进程内缓存），禁止直接 new。

### 请求与重试

- `POST {base_url}/rerank`，`Authorization: Bearer <key>`；
- 429 限速：优先按 `Retry-After` 等待，缺省按 `2s × 尝试次数` 退避，最多 3 次；
- 并发与超时由 `LLMGate.acquire("rerank")` 统一闸门控制。

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `httpx.AsyncClient` | HTTP 调用 |
| `LLMGate` | rerank 档并发/超时闸门 |
| `LLMCallLogger` | 调用日志（成本可观测） |
| `settings.RERANK_*` | 模型、地址、Key、并发与超时配置 |

---

## 4. 异常处理

- 文档为空或未配置 API Key：直接返回 `[]`，不发起请求；
- 任意异常（网络、鉴权、限流耗尽、响应格式错误）：记录 warning 并返回 `[]`，
  调用方保持混合检索原排序，主链路不中断；
- 响应中越界的文档下标：过滤掉，不写入结果；
- 调用日志写入失败：仅 warning，不影响重排序结果；
- 响应无计费字段：token 记 0，成本不影响日志落库。
