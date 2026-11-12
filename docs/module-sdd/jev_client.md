# SDD — JEV 客户端（jev_client）

> **代码位置**：`backend/app/services/jev_client.py`
> **协议**：TypeSafe System One（非 OpenAI 兼容）

---

## 1. 功能描述

封装腾讯云 EdgeOne Makers 内置 Jev 模型的 `/v1/systemone` 接口，供 RouterAgent 做意图判定。
只负责 HTTP 传输、超时与错误映射；不包含路由规则、Prompt 或降级策略。

JEV 不生成文本、不支持流式、不能走 `/v1/chat/completions`。它针对一段 `state`
并行判定一组强类型问题（`choice` / `score` / `noul`），返回选项、概率与置信度。

---

## 2. 接口签名

```python
class JevClient:
    def __init__(
        self,
        api_key: str,
        endpoint: str,
        model: str,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,  # 测试注入
    ) -> None: ...

    async def judge(self, state: dict, questions: dict) -> dict:
        """提交一次并行判定，返回原始 JSON。"""
```

通过 `LLMFactory.get_jev()` 获取进程内单例，禁止直接 new。
Key 优先读 `JEV_API_KEY`，兼容 `MAKERS_MODELS_KEY`（EdgeOne Makers 命名）。

### 请求

```json
{
  "model": "@makers/jev",
  "state": {"user_message": "...", "has_file": false, "file_type": null},
  "questions": {
    "intent": {
      "type": "choice",
      "instructions": "……判定规则……",
      "criteria": {"parse_list": "…", "chat": "…"}
    }
  }
}
```

### 响应

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "intent": {
      "type": "choice",
      "choice": "chat",
      "confidence": 0.42,
      "probabilities": {"chat": 0.42, "parse_list": 0.24}
    }
  },
  "usage": {"input_tokens": 612, "output_tokens": 18}
}
```

---

## 3. 错误映射

| 情况 | 异常 | 上层行为 |
|:---- |:---- |:---- |
| 连接失败、超时 | `LLMUnavailableError` | Router 静默降级 |
| HTTP 429 / 5xx / 529 | `LLMUnavailableError` | Router 静默降级 |
| HTTP 400 / 401 / 403 / 404 / 422 | `ConfigError` | 记录配置问题，静默降级 |
| 非 JSON 响应、缺少 `answers` | `LLMUnavailableError` | Router 静默降级 |
| `choice` 不在 6 类活跃意图内 | `LLMUnavailableError` | Router 静默降级 |

不重试：故障由 Router 的规则 + 轻量模型降级接管。

---

## 4. 置信度语义

- `confidence` 是概率分布的集中程度，**不是判对概率**；
- `probabilities` 是 6 类完整分布，按 Top1-Top2 差距辅助判断边界清晰度；
- 低于 `JEV_LOW_CONFIDENCE_THRESHOLD`（默认 0.60）时，Router 先降级到
  规则 + 轻量模型；降级结果仍低置信度或调用失败时，才设置
  `needs_confirmation=True`，由 ChatAgent 的 Hook 转人工确认；
- 规则只在 JEV 低置信度或调用失败时使用，不会改写 JEV 高置信度结果；
- “长期材料记忆”与“行业知识库”的区分由 JEV instructions 中的
  `_QUERY_SCOPE_GUIDE` 主判，低置信度时由轻量模型 prompt 再次区分。

---

## 5. 可观测性

`RouterAgent` 在每次调用后写 `LLMCallLogger`：

| 字段 | 取值 |
|:---- |:---- |
| `agent_name` | `RouterAgent.jev`；失败为 `RouterAgent.jev_error` |
| `model` | 响应中的 `model`（如 `jev-1.13.0`），失败时为配置值 |
| `input_tokens/output_tokens` | 响应 `usage`；失败记 0 |
| `cost` | 0（JEV 无公开计价） |
| `latency_ms` | 实际耗时 |

---

## 6. 测试

`backend/tests/test_jev_client.py` 使用 `httpx.MockTransport`，覆盖：
请求体与鉴权、成功响应、400/401/422 → `ConfigError`、429/5xx → `LLMUnavailableError`、
网络异常、非 JSON/缺 `answers`。测试不联网。

评测的 mock 模式会强制 `JEV_ENABLED=False`，保证零网络；real 模式通过
`JEV_API_KEY` 判断是否 SKIP。
