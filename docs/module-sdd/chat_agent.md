# SDD — 对话 Agent（chat_agent）

> **依据**：system-design.md §2.2.6，PRD §FR-8，tech-stack.md §7.5
> **代码位置**：`backend/app/agents/chat.py`
> **模型档位**：中量档（日常对话）

---

## 1. 功能描述

处理日常对话，流式输出（SSE）。
当用户询问材料历史报价、成交价或采购记录时，按需调用长期材料查询工具；工具查询带当前团队过滤，普通对话不调用该工具。
工具调用使用 OpenAI 兼容的标准闭环：保留模型原始 assistant 消息（包括供应商思考字段和 `tool_calls`），追加带原始 `tool_call_id` 的 tool 消息，再请求模型生成最终回答。
闭环支持多轮（上限 `MAX_TOOL_ROUNDS=3` 轮决策请求）：查询参数（材料名、供应商、日期区间）由模型依据工具 schema 自主决定，工具返回空结果或参数格式错误时模型可在下一轮换字段/换关键词重查（如公司名应从 material_name 换 supplier_name）；模型一轮都未调用工具时注入用户角色提醒后再给机会，轮次用尽仍要求工具时进入无 tools 的流式收尾（安全阀）。
工具筛选面覆盖 `MaterialHistoryFilter` 的材料名/供应商/日期区间；`team_id` 由服务端闭包绑定，模型不可传入。
管理会话上下文：保留最近 N 轮原文，超出压缩阈值时用轻量模型生成摘要。
上下文拼接遵循 tech-stack.md §7.6 顺序：System → 知识库 → 检索结果 → 摘要 → 最近N轮 → 当前输入。

### 低置信度路由人工确认

RouterAgent 返回 `needs_confirmation=True` 时（JEV 低置信度经规则/轻量模型降级后
仍不确定，或轻量模型调用失败），ChatAgent 调用 `route_hooks` 注册表。
默认 `ManualConfirmationHook` 返回 `confirm`，ChatAgent：

1. 先落库本轮 user 消息与 assistant 提示消息（metadata：
   `structured_type="route_confirm"`，`structured_data` 含 token/6 类选项/置信度/来源）；
2. 发送 `ChatChunk(delta=提示语, type="route_confirm", data=payload)`；
3. 发送 `done=true` 结束本轮，等待用户在弹窗中选择。

用户选择后，前端复用 `POST /api/chat` 提交
`pending_token + forced_intent`（取消时为 `forced_intent="chat"`、`route_cancelled=true`）：

- 服务端按 token 读取原始消息/附件，不信任客户端回传内容；
- 标记该待确认消息为 `resolved` / `cancelled`；
- 跳过再次保存 user 消息，只追加 assistant 回答；
- 构建上下文时取原始用户消息之前的历史，避免重复拼接原问题。

待确认状态存于 `Message.metadata_json`，有效期由 `ROUTE_CONFIRM_TTL_MINUTES` 控制（默认 30 分钟）。

### 行业知识问答（knowledge_query）

`route.intent == "knowledge_query"` 时，ChatAgent 调用
`chat_knowledge.answer_knowledge_question()`：

1. 去掉 `/知识` 前缀；空问题直接返回引导文本，不检索；
2. 调 `KnowledgeAgent().query(KnowledgeQueryInput(...), team_id, db)`；
3. 答案作为 `delta` 整段返回（KnowledgeAgent 目前非流式）；
4. 同时发 `type="knowledge"` 帧，data 含 `sources` 与 `results`（来源文件名/内容/相关度）；
5. 消息 metadata 存 `structured_type="knowledge"`，刷新后可恢复来源抽屉。

`generate_inquiry` / `compare` 不调用对应 Agent，只返回“请到采购单详情页操作”的引导。

---

## 2. 接口签名

```python
from collections.abc import AsyncGenerator
from app.schemas.chat import ChatInput, ChatChunk

class ChatAgent:

    async def chat_stream(
        self,
        data: ChatInput,          # 消息 + 会话 ID + 可选的人工确认续跑字段
        user_id: int,
        team_id: int,
        db: AsyncSession,
    ) -> AsyncGenerator[ChatChunk, None]:
        """流式对话，yield ChatChunk 直到完成。
        1. 加载会话消息（KnowledgeBaseManager.get_session_messages）
        2. 判断是否需要压缩（token 估算超阈值 70%）
           → 是：调用 LLMFactory.get_light() 生成摘要（不影响主模型配额）
        3. 拼接上下文（System → 知识库 → 摘要 → 最近N轮 → 当前输入）
        4. 普通对话调用 LLMFactory.get_medium().astream() 流式输出
        5. 历史材料问题执行多轮 assistant tool_calls ⇄ tool 闭环（≤MAX_TOOL_ROUNDS 轮），
           查询参数由模型按工具 schema 决定；模型未调用工具时走确定性兜底
        6. 最终回答流式输出并 yield 每个 token
        7. 完成后保存消息（KnowledgeBaseManager.add_message）
        8. 记录 LLMCallLogger.log()
        """
```

### Pydantic 模型（`backend/app/schemas/chat.py`）

```python
class ChatInput(BaseModel):
    message: str               # 用户当前输入
    session_id: int            # 会话 ID
    file_id: str | None        # 上传文件相对路径
    file_type: str | None      # list / quote
    file_name: str | None      # 原始文件名，用于消息展示
    forced_intent: RouteIntent | None = None  # 人工确认后的意图
    pending_token: str | None = None          # 待确认决策 token
    route_cancelled: bool = False             # 取消弹窗 → 按 chat 继续

class ChatChunk(BaseModel):
    delta: str                 # 增量 token（前端追加渲染）
    done: bool = False         # True 表示流式结束
    session_id: int
    type: str | None            # list / quote / route_confirm 等类型
    data: dict | None           # 结构化结果 / 待确认 payload

class MaterialHistoryToolInput(BaseModel):
    """长期材料查询工具的参数；由模型按 schema 自主填写，服务端只做格式校验。"""
    material_name: str | None   # 材料名称关键词；按供应商/日期查询时可留空
    supplier_name: str | None   # 供应商名称关键词
    date_from: str | None       # 报价日期起点 YYYY-MM-DD
    date_to: str | None         # 报价日期终点 YYYY-MM-DD
    # 校验：四项至少一项非空
```

### SSE 事件格式（API 层封装，Agent 层只 yield ChatChunk）

```
data: {"delta": "你好", "done": false, "session_id": 1}
data: {"delta": "，有什么", "done": false, "session_id": 1}
data: {"delta": "", "done": true, "session_id": 1}

# 低置信度路由确认帧（done 仍是最后一帧）
data: {"delta": "这条消息的意图不够明确，请确认要执行的操作。", "done": false,
       "session_id": 1, "type": "route_confirm",
       "data": {"token": "...", "status": "pending", "confidence": 0.42,
                "options": [{"intent": "chat", "executable": true, "...": "..."}]}}
data: {"delta": "", "done": true, "session_id": 1}
```

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `LLMFactory.get_medium()` | 主对话模型（流式） |
| `LLMFactory.get_light()` | 摘要压缩（轻量档） |
| `LLMCallLogger.log()` | 成本记录 |
| `KnowledgeBaseManager.get_session_messages()` | 加载历史消息 |
| `KnowledgeBaseManager.add_message()` | 保存新消息 |
| `MaterialHistoryService.list_records()` | 按需查询当前团队长期材料历史（工具内构造 `MaterialHistoryFilter`，含材料/供应商/日期筛选） |
| `app.agents.tool_loop.OpenAIToolLoop` | 保留 reasoning_content 和 tool_call_id，执行标准工具调用闭环 |
| `app.agents.route_hooks` | 低置信度路由 Hook 注册表与人工确认 payload |
| `app.agents.chat_knowledge` | 行业知识问答分发（KnowledgeAgent.query + knowledge 帧） |
| `app.services.route_decision.RouteDecisionService` | 待确认决策的读取、校验、关闭与续跑历史 |
| `app.agents.router.RouterAgent` | JEV 主路由 + 规则/轻量模型降级 |
| `app.core.config.settings.MEMORY_RECENT_TURNS` | 保留最近 N 轮（默认 6） |
| `app.core.config.settings.MEMORY_COMPRESS_THRESHOLD` | 压缩阈值（默认 0.7） |

### 上下文压缩规则

- 估算 token 数：每字符约 0.5 token（粗估，足够判断阈值）。
- 若当前上下文 token 估算 > 模型上限 × 阈值 → 触发压缩。
- 压缩后：早期消息替换为摘要，最近 N 轮保留原文。

---

## 4. 异常处理

| 异常 | 触发条件 | 处理策略 |
|:---- |:-------- |:-------- |
| `SessionNotFoundError` | session_id 不存在 | HTTP 404，流式未开始时直接返回错误 |
| `LLMUnavailableError` | 中量档 LLM 不可用 | yield 固定话术 token："服务暂时不可用，请稍后再试" |
| `RouteDecisionNotFoundError` | 待确认 token 不存在/不属于当前会话 | HTTP 404（流开始前由 API 预检拦截） |
| `RouteDecisionExpiredError` | 待确认选择超过 TTL | HTTP 410；流内兜底为提示文本 |
| `RouteDecisionResolvedError` | 同一 token 重复提交 | HTTP 409；流内兜底为"已处理"文本 |
| 压缩失败 | 轻量档摘要模型不可用 | 跳过压缩，直接截断超出部分（取最近 N 轮） |

### 工具调用协议

- 决策请求（非流式）携带 `tools`，材料历史语义命中时使用 `tool_choice=auto`；当前只注册长期材料工具，兼容 DeepSeek 思考模式不支持强制 function choice 的限制。
- 查询参数由模型按 `MaterialHistoryToolInput` schema 自主决定（材料名、供应商、日期区间）；服务端不再用正则预提取或 `expected_tool_args` 锁定参数，仅做 schema 校验与日期格式解析（解析失败返回错误 JSON，模型可在下一轮自纠）。`team_id` 与数据库会话由服务端闭包绑定，不属于工具参数。
- 闭环支持多轮：每轮决策请求都携带 `tools`，模型返回 `tool_calls` 则执行并回传，最多 `MAX_TOOL_ROUNDS=3` 轮；轮次用尽仍要求工具时进入安全阀——发送不带 `tools` 的最终流式请求强制生成文本回答，避免无界工具循环。
- 模型未调用工具的轮次处理：若尚未执行过任何工具且仍有剩余轮次，向 payload 追加一条用户角色的提醒消息（"必须调用工具查询"）后继续下一轮；剩余轮次用尽仍未调用工具时静默返回（不输出自答），由调用方降级。
- 模型返回的 assistant 消息必须原样保留 `reasoning_content`、`tool_calls`、工具名称、参数和调用 ID。
- 工具执行结果以 `role=tool` 回传，`tool_call_id` 必须与 assistant 返回的 ID 完全一致，结果内容使用 JSON 文本。
- 最终流式请求继续携带前述 assistant/tool 消息，但不再携带 `tools` 与工具选择约束，避免思考模式对 `none` 或强制 function choice 的兼容性问题。
- 工具空结果必须携带可执行指引：按当前条件查不到记录时，工具返回 `{"results": [], "hint": "…"}`；material_name 查空时由 `MaterialHistoryService.suggest_suppliers` 确定性检查关键词是否匹配团队内供应商名，匹配则在 `hint` 中明确指示改用 `supplier_name` 重查并附 `supplier_match` 列表——把换字段建议放到模型决策点上，而不是依赖模型记住 system prompt。
- 历史问题回答必须依据工具记录：提醒重试后模型仍未调用任何工具时，其自答内容一律丢弃，走确定性降级——正则提取关键词（词表与意图门控保持同步，含裸"成交价/报价"）后先按 material_name 直查工具，查空再按 supplier_name 直查，仍为空或提取不到时提示用户补充材料名；直查结果以 `_format_material_history_result` 格式化输出。
- `ChatOpenAI` 的通用 LangChain 转换层不会自动回传供应商扩展的 `reasoning_content`，因此历史材料工具调用使用 LLMFactory 返回实例的 OpenAI 兼容异步客户端完成协议序列化。
