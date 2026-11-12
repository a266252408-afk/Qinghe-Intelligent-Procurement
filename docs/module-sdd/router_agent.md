# SDD — 主控 Router Agent（router_agent）

> **依据**：system-design.md §2.2.1，tech-stack.md §7.3，CLAUDE.md §6
> **代码位置**：`backend/app/agents/router.py`
> **主模型**：JEV（TypeSafe System One，强类型判定）
> **降级模型**：轻量档 LLM + 确定性规则

---

## 1. 功能描述

接收用户原始输入（文本 + 可选文件标志），识别 6 类意图之一。
**所有消息先交给 JEV 判断**；只有 JEV 不可用或调用失败时，才静默降级到现有规则层与轻量档 LLM。

### 1.1 决策链

```
JEV（主路由，含附件/斜杠命令）
  ├─ confidence ≥ JEV_LOW_CONFIDENCE_THRESHOLD（默认 0.60）
  │    → 直接按 JEV 意图执行
  └─ confidence < 阈值 / JEV 失败（超时/429/5xx/协议错误/未知意图）
       → 规则层：附件 → 斜杠命令（/知识、/历史、/询价、/比价）→ 历史价格关键词
       → 规则未命中：轻量档 LLM（_llm_route）
            ├─ confidence ≥ 阈值 → 直接执行
            └─ confidence < 阈值 / 调用失败
                 → needs_confirmation=True → 现有 Hook → 人工确认弹窗
```

规则层不再前置短路。正常路径下 `rt_val_21` 一类“记录 + 成交价”的规则冲突不会出现；
只有 JEV 低置信度或故障降级时才沿用旧规则行为。JEV 高置信度结果不会被规则改写。

### 1.1.1 长期材料记忆 vs 行业知识库

`_QUERY_SCOPE_GUIDE` 同时拼进 JEV instructions 与轻量模型 system prompt：

- `chat`（长期材料记忆）：本团队自己的历史成交价、历史报价、采购记录、
  供应商报价记录、某材料我们买过/上次买/以前报价、长期记忆。
- `knowledge_query`（行业知识库）：公开的行业规范、验收标准、养护方法、
  病虫害防治、修剪/施肥/浇水/移栽、成活率、种植密度、土壤等通用知识。

判断口诀：出现“我们/上次/买过/成交价/采购记录/供应商报价记录”优先 chat；
出现“规范/标准/怎么养护/病虫害/修剪/施肥/浇水/移栽/成活率”优先 knowledge_query；
两类信号同时出现时看用户主要想要哪一类，无法判断时 confidence 给 0.6 以下。

### 1.2 6 类意图与目标 Agent

| 意图 | 目标 Agent | 说明 |
|:---- |:-------- |:-------- |
| `parse_list` | ListParserAgent | 解析采购清单 |
| `parse_quote` | QuoteParseAgent | 解析报价单 |
| `generate_inquiry` | InquiryAgent | 生成询价单 |
| `compare` | CompareAgent | 比价 |
| `knowledge_query` | KnowledgeAgent | 行业知识检索（仅公共知识，不查团队交易记录） |
| `chat` | ChatAgent | 通用对话 / 长期材料记忆 |

---

## 2. 接口签名

```python
from app.schemas.router import RouterInput, RouteResult

class RouterAgent:
    async def route(
        self,
        data: RouterInput,        # 用户输入 + 附件元信息
        team_id: int,
        db: AsyncSession,
    ) -> RouteResult:
        """JEV 优先；失败时降级规则 + 轻量模型。"""
```

### Pydantic 模型（`backend/app/schemas/router.py`）

```python
RouteIntent = Literal[...]  # 6 类活跃意图的唯一来源

class RouterInput(BaseModel):
    message: str
    has_file: bool = False
    file_type: str | None = None
    session_id: str = ""

class RouteResult(BaseModel):
    intent: RouteIntent
    target_agent: str
    extracted_params: dict = {}
    confidence: float = 1.0
    probabilities: dict[str, float] = {}   # JEV 6 类概率；规则/轻量模型为空
    source: str = "light_llm"              # jev / rule / light_llm / light_llm_fallback / manual
    needs_confirmation: bool = False       # JEV 与轻量模型低置信度时为 True
```

---

## 3. JEV 请求契约

- Endpoint：`POST {JEV_ENDPOINT}`，默认 `https://ai-gateway.edgeone.link/v1/systemone`
- 鉴权：`Authorization: Bearer $JEV_API_KEY`
- 模型：`JEV_MODEL`，默认 `@makers/jev`
- 请求体：`{"model", "state", "questions"}`
  - `state`：`user_message`、`has_file`、`file_type`、`known_commands`、`channel`
  - `questions.intent`：`type=choice`，6 个 criteria
  - 判定规则全部写在 `instructions`；问题 ID 不会发送给模型
- 响应：`answers.intent.choice / confidence / probabilities`，`usage.input_tokens/output_tokens`

详细客户端契约见 `docs/module-sdd/jev_client.md`。

---

## 4. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `LLMFactory.get_jev()` | JEV 客户端（进程内缓存） |
| `LLMFactory.get_light()` | JEV 故障后的轻量档降级 |
| `LLMGate.run("jev", ...)` | JEV 并发闸门与超时 |
| `LLMCallLogger.log()` | 记录 JEV/轻量模型调用；JEV 失败也记 0 token 日志 |
| `app.agents.route_hooks` | 低置信度转人工确认的 Hook 注册表 |

### 配置项

| 配置 | 默认 | 说明 |
|:---- |:---- |:---- |
| `JEV_ENABLED` | `True` | 关闭后直接走降级 |
| `JEV_API_KEY` / `MAKERS_MODELS_KEY` | 空 | 二选一；为空时视为不可用，保证测试/CI 不联网 |
| `JEV_ENDPOINT` | EdgeOne 网关 | 可替换代理/私有部署 |
| `JEV_MODEL` | `@makers/jev` | 固定别名 |
| `JEV_CONCURRENCY` | 24 | 进程内在途上限 |
| `JEV_TIMEOUT_S` | 10.0 | 单次调用超时 |
| `JEV_LOW_CONFIDENCE_THRESHOLD` | 0.60 | JEV 低于该值先降级；降级仍低于该值才触发人工确认 |

---

## 5. 异常处理

| 异常 | 触发条件 | 处理策略 |
|:---- |:-------- |:-------- |
| `ConfigError` | JEV Key 无效、请求体非法 | 记录 warning，静默降级规则 + 轻量模型 |
| `LLMUnavailableError` | JEV 超时、429、5xx、协议异常、未知意图 | 同上 |
| 轻量模型异常 | 降级链路也失败 | 返回 `chat`、`confidence=0.5`、`source=light_llm_fallback`、`needs_confirmation=True`，转人工确认 |
| 低置信度 | JEV `confidence < 阈值` | 先走规则 + 轻量模型降级；降级仍低置信度才由 Hook 转人工确认 |

**用户可见行为**：JEV 故障降级对用户静默，不插入额外提示；仅日志与 `LLMCallLogger` 记录。
