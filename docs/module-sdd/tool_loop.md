# SDD — 工具调用闭环（tool_loop）

> **代码位置**：`backend/app/agents/tool_loop.py`
> **定位**：OpenAI 兼容协议的 assistant `tool_calls` ⇄ `tool` 多轮闭环。
> **约束**：只做协议编排，不定义业务工具；工具由调用方注册，由 LLMFactory 提供模型实例。

---

## 1. 功能描述

在对话中执行"模型请求工具 → 服务端执行 → 结果回传 → 模型继续"的多轮闭环，并保留：

- 供应商思考字段 `reasoning_content`；
- 模型返回的原始工具调用 `id`；
- 工具执行的原始结果，供调用方做确定性降级。

轮次上限 `MAX_TOOL_ROUNDS = 3`。轮次用尽时走安全阀：发送不带 `tools` 的流式请求，
强制模型基于已有工具结果生成文本回答，避免无界工具循环。

---

## 2. 接口签名

```python
MAX_TOOL_ROUNDS = 3

class OpenAIToolLoop:
    def __init__(
        self,
        llm: Any,                       # LLMFactory 返回的 LangChain 模型
        tools: list[BaseTool],          # 已注册业务工具
        session_id: str | None = None,  # 用于 LLM 调用日志
        db: AsyncSession | None = None, # 日志落库；为空则不记录
    ) -> None: ...

    async def stream(
        self,
        messages: list[BaseMessage],
        required_tool: str | None = None,               # 问题必须调用的工具
        expected_tool_args: dict[str, Any] | None = None,  # 服务端已识别的查询参数
    ) -> AsyncGenerator[str, None]:
        """逐段产出最终文本（SSE 增量）。"""
```

### 执行流程

1. 非流式请求模型决策（`stream=False`，携带 `tools`），完整保存原始响应；
2. 模型返回 `tool_calls`：按原始 ID 逐个执行工具，追加 `tool` 消息后进入下一轮；
3. 模型不返回工具、且此前已执行过工具：直接流式输出内容并结束；
4. 指定了 `required_tool` 但模型一轮都未调用：注入一次用户角色提醒后再给一轮机会；
5. 轮次用尽仍要求工具：安全阀——发不带 `tools` 的流式请求生成最终文本；
6. 全程经 `LLMGate.acquire("medium")` 排队，并按次记录 `LLMCallLogger`。

### 工具参数校验

`expected_tool_args` 中的键值必须与模型实际参数一致，防止模型把材料名查成别的对象；
不一致时该次工具调用返回错误 JSON，由模型自行纠正。

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `langchain_core` 消息与工具类型 | 消息序列化、`convert_to_openai_tool` |
| `app.services.llm_gate.LLMGate` | 中量档并发闸门与超时 |
| `app.services.llm_logger.LLMCallLogger` | 每次原始调用记录 token 与耗时 |
| `llm.async_client.chat.completions` | 非流式决策与流式收尾 |

---

## 4. 异常处理

- 模型返回未知工具或缺少调用 ID：抛出 `ValueError`，由上层转统一错误响应；
- 工具执行失败：把 `{"error": "工具执行失败：..."}` 作为工具结果回传，让模型继续决策；
- 模型拒绝调用必需工具且轮次用尽：返回空内容，`last_results` 为空，由调用方走确定性降级；
- 流式请求在未输出任何内容前失败：退避 1 秒重试一次；已输出内容则直接上抛，避免重复文本；
- LLM 调用日志写入失败：仅记录 warning，不阻断闭环；
- 模型未提供 OpenAI 兼容 `async_client`：抛出 `TypeError`，属于配置错误。
