# SDD — 待确认路由决策服务（route_decision）

> **代码位置**：`backend/app/services/route_decision.py`
> **定位**：低置信度路由的人工确认状态读取、校验与关闭。
> **设计**：不新建表，状态持久化在 assistant 消息的 `metadata_json` 中。

---

## 1. 功能描述

当路由 Hook 判定需要人工确认时，ChatAgent 会把确认 payload 写入 assistant 消息的
`metadata_json`（`structured_type = "route_confirm"`）。本服务负责：

- 按 token 读取待确认决策，并校验会话归属、状态与有效期；
- 用户选择或取消后，把状态标记为 `resolved` / `cancelled`；
- 续跑时取原始用户消息之前的历史，避免重复拼接当前问题。

选择复用既有消息表，避免为一次性交互增加独立表与迁移。

---

## 2. 接口签名

```python
class RouteDecisionService:
    @staticmethod
    async def get_pending(
        session_id: int,
        user_id: int,      # 校验会话归属
        token: str,        # 确认令牌
        db: AsyncSession,
    ) -> PendingRoute: ...

    @staticmethod
    async def mark_resolved(
        message_id: int,
        chosen_intent: str,
        cancelled: bool,
        user_id: int,
        db: AsyncSession,
    ) -> None: ...

    @staticmethod
    async def get_history_before(
        session_id: int,
        user_id: int,
        before_message_id: int,
        db: AsyncSession,
    ) -> list[MessageOut]: ...
```

### 状态与有效期

- `status`：`pending` → `resolved` / `cancelled`；
- 有效期：`created_at + ttl_minutes`（缺省取 `settings.ROUTE_CONFIRM_TTL_MINUTES`）；
- 读取时过滤已下线意图，只返回 `ACTIVE_INTENTS` 中的选项。

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `Message` / `ConversationSession` | 读取与更新确认状态 |
| `KnowledgeBaseManager.ensure_session_owned` | 会话归属校验 |
| `PendingRoute` / `RouteOption` / `MessageOut` | 读模型 |
| `settings.ROUTE_CONFIRM_TTL_MINUTES` | 默认有效期 |

---

## 4. 异常处理

| 场景 | 异常 | HTTP |
|:---- |:---- |:---- |
| 会话不属于当前用户 | `RouteDecisionNotFoundError` | 404 |
| token 不存在 | `RouteDecisionNotFoundError` | 404 |
| 已选择/已取消后重复提交 | `RouteDecisionResolvedError` | 409 |
| 超过有效期 | `RouteDecisionExpiredError` | 410 |
| metadata 缺字段或格式错误 | `RouteDecisionNotFoundError` | 404（不暴露 500） |

- 无 `created_at` 的旧数据视为不过期，兼容历史消息；
- 更新时整体赋值新的 `metadata_json` 字典，确保 SQLAlchemy 检测到 JSON 字段变更；
- 写入后 `flush`，事务提交由请求层统一负责。
