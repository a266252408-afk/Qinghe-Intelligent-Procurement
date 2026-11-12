"""审批服务
依据：docs/module-sdd/approval_service.md
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    MissingRejectReasonError,
    OrderNotFoundError,
    PermissionDeniedError,
)
from app.models.approval import ApprovalRecord
from app.models.order import PurchaseOrder
from app.models.project import Project
from app.models.user import User
from app.schemas.approval import ApprovalOut, PendingListOut, PendingOrderOut
from app.services.order_service import PurchaseOrderService


def _record_to_out(record: ApprovalRecord) -> ApprovalOut:
    return ApprovalOut(
        record_id=record.id,
        order_id=record.order_id,
        approver_id=record.approver_id,
        decision=record.decision,
        reason=record.reason,
        created_at=record.created_at,
    )


class ApprovalService:

    @staticmethod
    async def approve(
        order_id: int,
        approver_id: int,
        team_id: int,
        db: AsyncSession,
        role: str | None = None,
    ) -> ApprovalOut:
        """审批下单申请：pending_approval → ordered，并生成下单记录。"""
        _assert_approver(role)
        order = await _load_order(order_id, team_id, db)
        if order.status != "pending_approval":
            raise PermissionDeniedError(f"采购单当前状态 {order.status} 不可审批")

        order.status = "approved"
        order.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await PurchaseOrderService.create_supplier_order(order_id, team_id, db)

        record = ApprovalRecord(
            order_id=order_id,
            approver_id=approver_id,
            decision="approved",
        )
        db.add(record)
        await db.flush()
        return _record_to_out(record)

    @staticmethod
    async def reject(
        order_id: int,
        approver_id: int,
        reason: str | None,
        team_id: int,
        db: AsyncSession,
        role: str | None = None,
    ) -> ApprovalOut:
        """驳回下单申请：pending_approval → draft（必须填写原因）。"""
        if not reason or not reason.strip():
            raise MissingRejectReasonError()

        _assert_approver(role)
        order = await _load_order(order_id, team_id, db)
        if order.status != "pending_approval":
            raise PermissionDeniedError(f"采购单当前状态 {order.status} 不可审批")

        order.status = "draft"
        order.updated_at = datetime.now(timezone.utc)

        record = ApprovalRecord(
            order_id=order_id,
            approver_id=approver_id,
            decision="rejected",
            reason=reason.strip(),
        )
        db.add(record)
        await db.flush()
        return _record_to_out(record)

    @staticmethod
    async def list_pending(team_id: int, db: AsyncSession, role: str | None = None) -> PendingListOut:
        """查询团队内所有待审批采购单列表"""
        _assert_approver(role)
        stmt = (
            select(PurchaseOrder, Project.name, User.display_name, User.username)
            .join(Project, PurchaseOrder.project_id == Project.id)
            .join(User, PurchaseOrder.creator_id == User.id)
            .where(
                Project.team_id == team_id,
                Project.is_deleted.is_(False),
                PurchaseOrder.status == "pending_approval",
            )
            .order_by(PurchaseOrder.updated_at.asc())
        )
        rows = (await db.execute(stmt)).all()
        items = [
            PendingOrderOut(
                order_id=o.id,
                project_id=o.project_id,
                project_name=project_name,
                name=o.name,
                creator_id=o.creator_id,
                creator_name=display_name or username,
                total_amount=float(o.total_amount) if o.total_amount is not None else None,
                remark=o.remark,
                updated_at=o.updated_at,
            )
            for o, project_name, display_name, username in rows
        ]
        return PendingListOut(total=len(items), items=items)

    @staticmethod
    async def get_approval_history(order_id: int, team_id: int, db: AsyncSession) -> list[ApprovalOut]:
        """查询采购单的全部审批记录"""
        await _load_order(order_id, team_id, db)  # 权限校验

        stmt = (
            select(ApprovalRecord)
            .where(ApprovalRecord.order_id == order_id)
            .order_by(ApprovalRecord.created_at.asc())
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [_record_to_out(r) for r in rows]


async def _load_order(order_id: int, team_id: int, db: AsyncSession) -> PurchaseOrder:
    """通过 project 链路校验 team_id，防越权"""
    stmt = (
        select(PurchaseOrder)
        .join(Project, PurchaseOrder.project_id == Project.id)
        .where(PurchaseOrder.id == order_id, Project.team_id == team_id)
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if order is None:
        raise OrderNotFoundError()
    return order


def _assert_approver(role: str | None) -> None:
    """校验审批角色；None 仅用于兼容底层旧调用，API 必须传入角色。"""
    if role is not None and role != "owner":
        raise PermissionDeniedError("只有团队管理员可以审批")
