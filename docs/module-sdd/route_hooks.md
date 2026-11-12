# SDD — 路由 Hook（route_hooks）

> **代码位置**：`backend/app/agents/route_hooks.py`
> **定位**：路由结果返回后、执行意图前的可插拔决策点。

---

## 1. 功能描述

提供注册式 Hook 链：按注册顺序执行，首个返回非 `continue` 的 Hook 生效。
默认注册 `ManualConfirmationHook`——当路由结果 `needs_confirmation` 为真
（JEV 或轻量模型低置信度）时，把本次请求转成人工确认弹窗，而不是直接执行意图。
规则路由（`source=rules`）永不触发确认。

后续审计、告警等能力只需注册新 Hook，不修改 ChatAgent，遵循开闭原则。

---

## 2. 接口签名

```python
@dataclass
class RouteHookContext:
    message: str
    session_id: int
    user_id: int
    team_id: int
    route: RouteResult                 # 路由结果（intent/source/confidence/...）
    has_file: bool = False
    file_type: str | None = None
    file_id: str | None = None
    file_name: str | None = None
    upload_id: int | None = None

@dataclass
class RouteHookResult:
    action: Literal["continue", "confirm"]
    payload: dict | None = None

class RouteHook(Protocol):
    async def __call__(self, ctx: RouteHookContext) -> RouteHookResult: ...

class RouteHookRegistry:
    def register(self, hook: RouteHook) -> None: ...
    async def dispatch(self, ctx: RouteHookContext) -> RouteHookResult: ...

def build_confirm_payload(ctx: RouteHookContext, user_message_id: int) -> dict:
    """生成 RouteConfirmPayload 并序列化为 JSON 字典。"""

route_hook_registry = RouteHookRegistry()
route_hook_registry.register(ManualConfirmationHook())
```

### 确认选项

`build_confirm_payload` 输出 `RouteConfirmPayload`，包含 6 类活跃意图，按概率降序，
并标记每项在当前上下文是否可执行：

| 意图 | 可执行条件 | 不可执行提示 |
|:---- |:---- |:---- |
| `parse_list` | 已上传清单文件（`file_type=list`） | 需要先上传采购清单文件 |
| `parse_quote` | 已上传报价单（`file_type=quote`） | 需要先上传供应商报价单 |
| `generate_inquiry` | 否 | 当前仅提示到采购单详情页操作 |
| `compare` | 否 | 当前仅提示到采购单详情页操作 |
| `knowledge_query` | 是 | — |
| `chat` | 是 | — |

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `settings.JEV_LOW_CONFIDENCE_THRESHOLD` | 写入确认 payload 的置信度阈值 |
| `settings.ROUTE_CONFIRM_TTL_MINUTES` | 待确认选择的有效期 |
| `app.schemas.router` | `RouteResult` / `RouteOption` / `RouteConfirmPayload` |

---

## 4. 异常处理

- 默认 Hook 只做纯逻辑判断，无 I/O，不产生异常路径。
- 新增 Hook 必须保证幂等，并能在不适用时安全返回 `continue`。
- Hook 抛出的异常会中断本次请求；审计/告警类 Hook 建议内部吞掉异常并记录日志。
- `user_message_id` 在消息落库后才可知，因此 Hook 阶段只返回 `action="confirm"` 且
  `payload=None`，由 ChatAgent 落库后调用 `build_confirm_payload` 补齐。
