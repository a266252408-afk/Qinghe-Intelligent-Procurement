# SDD — 审批流服务（approval_service）

> **依据**：system-design.md §2.2.9，PRD §FR-9，PRD §4.2
> **代码位置**：`backend/app/services/approval_service.py`

---

## 1. 功能描述

管理采购单的审批记录与状态流转。
主管通过/驳回采购单，驳回时需填写原因。
记录操作人、时间、决策到 `approval_records` 表，同步触发 `PurchaseOrderService.update_status()`。
不调用大模型。

---

## 2. 接口签名

```python
from app.schemas.approval import (
    ApprovalAction, ApprovalRecordOut, ApprovalListOut
)

class ApprovalService:

    @staticmethod
    async def approve(
        order_id: int,
        approver_id: int,         # 审批人用户 ID（必须是 owner 角色）
        team_id: int,
        db: AsyncSession,
    ) -> ApprovalRecordOut:
        """审批通过：pending_approval → approved；写入 approval_records。"""

    @staticmethod
    async def reject(
        order_id: int,
        approver_id: int,
        reason: str,              # 驳回原因（必填）
        team_id: int,
        db: AsyncSession,
    ) -> ApprovalRecordOut:
        """驳回：pending_approval → rejected；reason 不可为空。"""

    @staticmethod
    async def list_pending(
        approver_id: int,         # 主管 ID
        team_id: int,
        db: AsyncSession,
    ) -> ApprovalListOut:
        """查询该团队所有待审批（status=pending_approval）的采购单，按提交时间倒序。"""

    @staticmethod
    async def get_record(
        order_id: int,
        team_id: int,
        db: AsyncSession,
    ) -> ApprovalRecordOut | None:
        """查询某采购单最新一条审批记录（用于展示驳回原因）。"""
```

### Pydantic 模型（`backend/app/schemas/approval.py`）

```python
class ApprovalAction(BaseModel):
    reason: str | None    # 驳回时必填；通过时可为 None

class ApprovalRecordOut(BaseModel):
    record_id: int
    order_id: int
    approver_id: int
    decision: str          # "approved" / "rejected"
    reason: str | None
    created_at: datetime

class ApprovalListOut(BaseModel):
    total: int
    items: list[PendingOrderOut]  # 返回审批页所需的采购单摘要

class PendingOrderOut(BaseModel):
    order_id: int
    project_id: int
    project_name: str
    creator_id: int
    creator_name: str
    total_amount: float | None
    remark: str | None
    updated_at: datetime
```

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `SQLAlchemy AsyncSession` | 写入 approval_records |
| `app.models.approval.ApprovalRecord` | ORM |
| `app.services.order_service.PurchaseOrderService` | 触发状态变更 |
| `app.core.exceptions` | OrderNotFoundError, PermissionError, InvalidStatusTransitionError |

---

## 4. 异常处理

| 异常类 | 触发条件 | HTTP 状态码 |
|:------- |:-------- |:----------- |
| `OrderNotFoundError` | 采购单不存在 | 404 |
| `PermissionError` | 操作者不是 owner 角色 | 403 |
| `InvalidStatusTransitionError` | 采购单不处于 pending_approval 状态 | 422 |
| `MissingRejectReasonError` | 驳回时 reason 为空或空字符串 | 422 |
