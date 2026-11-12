# SDD — 采购单管理服务（order_service）

> **依据**：system-design.md §2.2.8，PRD §FR-1，PRD §4.1 状态机
> **代码位置**：`backend/app/services/order_service.py`

---

## 1. 功能描述

管理采购单（PurchaseOrder）和采购项（PurchaseItem）的完整生命周期。
支持采购单自定义名称和草稿基本信息编辑。
维护采购单状态机，确保状态流转合法。
支持按项目、按状态、按时间筛选采购单列表。
不调用大模型。

### 状态机

```
草稿(draft) → 待审批(pending_approval) → 已通过(approved) → 已下单(ordered)
                                                               → 已收货(received) → 已对账(settled)
           → 已驳回(rejected)  ─────────────────────────────→ 草稿(draft)（修改后重提）
```

合法转换表：

| 当前状态 | 可转换到 | 触发方 |
|:-------- |:-------- |:------ |
| draft | pending_approval | 采购员（submit） |
| pending_approval | approved / rejected | 采购主管（approve / reject） |
| approved | ordered | 系统（confirm_order） |
| ordered | received | 采购员（confirm_receipt） |
| received | settled | 采购员（confirm_settlement） |
| rejected | draft | 采购员（resubmit，修改后） |

---

## 2. 接口签名

```python
from app.schemas.order import (
    OrderCreate, OrderOut, OrderListOut,
    OrderItemCreate, OrderItemOut, OrderStatusUpdate
)

class PurchaseOrderService:

    @staticmethod
    async def create_order(
        data: OrderCreate,        # 包含 project_id / name / remark
        creator_id: int,
        team_id: int,
        db: AsyncSession,
    ) -> OrderOut:
        """创建采购单，初始状态为 draft。"""

    @staticmethod
    async def update_order(
        order_id: int,
        data: OrderUpdate,        # 草稿采购单名称和备注
        team_id: int,
        db: AsyncSession,
    ) -> OrderOut:
        """更新草稿采购单的名称和备注。"""

    @staticmethod
    async def get_order(
        order_id: int,
        team_id: int,             # 防越权
        db: AsyncSession,
    ) -> OrderOut:
        """查询采购单详情（含采购项列表）。"""

    @staticmethod
    async def list_orders(
        team_id: int,
        project_id: int | None,   # 按项目筛选
        status: str | None,       # 按状态筛选
        creator_id: int | None,   # 采购员仅查自己，主管可查全团队
        db: AsyncSession,
    ) -> OrderListOut:
        """查询采购单列表，按更新时间倒序。"""

    @staticmethod
    async def save_items(
        order_id: int,
        items: list[OrderItemCreate],  # AI 解析确认后的采购项列表
        team_id: int,
        db: AsyncSession,
    ) -> list[OrderItemOut]:
        """覆盖保存采购项（先删旧项，再批量插入）。"""

    @staticmethod
    async def submit_for_approval(
        order_id: int,
        team_id: int,
        db: AsyncSession,
    ) -> OrderOut:
        """提交审批：draft → pending_approval；采购项为空则拒绝。"""

    @staticmethod
    async def update_status(
        order_id: int,
        new_status: str,          # 目标状态
        team_id: int,
        db: AsyncSession,
    ) -> OrderOut:
        """通用状态更新（由 ApprovalService 或内部调用），校验合法转换。"""

    @staticmethod
    async def confirm_receipt(
        order_id: int,
        team_id: int,
        db: AsyncSession,
    ) -> OrderOut:
        """确认收货：ordered → received。"""

    @staticmethod
    async def delete_order(
        order_id: int,
        team_id: int,
        db: AsyncSession,
    ) -> None:
        """删除当前团队采购单及其询价、报价管理记录，长期材料历史保留。"""
```

### Pydantic 模型（`backend/app/schemas/order.py`）

```python
class OrderCreate(BaseModel):
    project_id: int
    remark: str | None

class OrderItemCreate(BaseModel):
    species: str            # 苗木品种
    spec: str               # 规格，如"胸径12cm"
    quantity: float         # 数量
    unit: str               # 单位，如"株"
    unit_price: float | None
    total_price: float | None

class OrderItemOut(OrderItemCreate):
    item_id: int
    order_id: int

class OrderOut(BaseModel):
    order_id: int
    project_id: int
    creator_id: int
    status: str
    total_amount: float | None
    remark: str | None
    items: list[OrderItemOut]
    created_at: datetime
    updated_at: datetime

class OrderListOut(BaseModel):
    total: int
    items: list[OrderOut]

class OrderStatusUpdate(BaseModel):
    status: str             # 目标状态
```

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `SQLAlchemy AsyncSession` | CRUD |
| `app.models.order.PurchaseOrder` | ORM |
| `app.models.order_item.PurchaseItem` | ORM |
| `app.core.exceptions` | OrderNotFoundError, InvalidStatusTransitionError |

---

## 4. 异常处理

| 异常类 | 触发条件 | HTTP 状态码 |
|:------- |:-------- |:----------- |
| `OrderNotFoundError` | order_id 不存在或 team_id 不匹配 | 404 |
| `InvalidStatusTransitionError` | 状态转换不在合法表中 | 422 |
| `EmptyOrderError` | 提交审批时采购项为空 | 422 |
| `PermissionError` | 无权操作 | 403 |

删除采购单前会清理采购项、询价单、报价及报价项；长期材料历史记录解除报价来源关联后保留。
