"""审批服务测试"""
import pytest
from sqlalchemy import select

from app.services.auth_service import AuthService
from app.services.project_service import ProjectService
from app.services.order_service import PurchaseOrderService
from app.services.approval_service import ApprovalService
from app.schemas.auth import LoginRequest, TeamCreate
from app.schemas.order import OrderCreate, OrderItemCreate
from app.schemas.project import ProjectCreate
from app.core.exceptions import MissingRejectReasonError, PermissionDeniedError
from app.core.security import decode_token
from app.models.supplier_order import SupplierOrder


pytestmark = pytest.mark.asyncio


async def _make_pending_order(db):
    """创建一个处于 pending_approval 状态的采购单，返回 (uid, team_id, order_id)"""
    token = await AuthService.login_or_register(LoginRequest(username="approver_user", password="p"), db)
    uid = decode_token(token.access_token)["user_id"]
    team = await AuthService.create_team(uid, TeamCreate(name="AT"), db)
    project = await ProjectService.create_project(ProjectCreate(name="P"), uid, team.team_id, db)
    order = await PurchaseOrderService.create_order(
        OrderCreate(project_id=project.project_id), uid, team.team_id, db
    )
    await PurchaseOrderService.save_items(
        order.order_id,
        [OrderItemCreate(species="松树", spec="高3m", quantity=2, unit="棵")],
        team.team_id, db,
    )
    await PurchaseOrderService.submit_for_approval(order.order_id, team.team_id, db)
    return uid, team.team_id, order.order_id


async def test_approve_order(db):
    uid, team_id, oid = await _make_pending_order(db)
    record = await ApprovalService.approve(oid, uid, team_id, db)
    assert record.decision == "approved"
    supplier_order = await db.scalar(
        select(SupplierOrder).where(SupplierOrder.purchase_order_id == oid)
    )
    assert supplier_order is not None
    assert supplier_order.status == "ordered"


async def test_reject_order_with_reason(db):
    uid, team_id, oid = await _make_pending_order(db)
    record = await ApprovalService.reject(oid, uid, "价格偏高", team_id, db)
    assert record.decision == "rejected"
    assert "价格" in record.reason


async def test_reject_without_reason_raises(db):
    uid, team_id, oid = await _make_pending_order(db)
    with pytest.raises(MissingRejectReasonError):
        await ApprovalService.reject(oid, uid, None, team_id, db)


async def test_list_pending_returns_correct(db):
    uid, team_id, oid = await _make_pending_order(db)
    result = await ApprovalService.list_pending(team_id, db)
    assert result.total == 1
    assert result.items[0].order_id == oid


async def test_approve_non_pending_raises(db):
    uid, team_id, oid = await _make_pending_order(db)
    await ApprovalService.approve(oid, uid, team_id, db)  # 先通过
    # 再次审批应报错（状态已是 approved）
    with pytest.raises(PermissionDeniedError):
        await ApprovalService.approve(oid, uid, team_id, db)
