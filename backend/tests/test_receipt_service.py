"""收货单生成、到货时间和确认联动测试。"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.exceptions import InvalidStatusTransitionError
from app.core.security import decode_token
from app.models.order import PurchaseOrder
from app.models.supplier_order import SupplierOrder
from app.models.material_history import MaterialHistoryRecord
from app.models.receipt import Receipt
from app.services.approval_service import ApprovalService
from app.services.auth_service import AuthService
from app.services.order_service import PurchaseOrderService
from app.services.project_service import ProjectService
from app.services.receipt_service import ReceiptService
from app.schemas.auth import LoginRequest, TeamCreate
from app.schemas.order import OrderCreate, OrderItemCreate
from app.schemas.project import ProjectCreate
from app.schemas.receipt import ReceiptItemUpdate, ReceiptUpdate

pytestmark = pytest.mark.asyncio


async def _setup_approved(db):
    token = await AuthService.login_or_register(LoginRequest(username="receipt_user", password="p"), db)
    user_id = decode_token(token.access_token)["user_id"]
    team = await AuthService.create_team(user_id, TeamCreate(name="收货团队"), db)
    project = await ProjectService.create_project(ProjectCreate(name="收货项目"), user_id, team.team_id, db)
    order = await PurchaseOrderService.create_order(OrderCreate(project_id=project.project_id), user_id, team.team_id, db)
    await PurchaseOrderService.save_items(
        order.order_id,
        [OrderItemCreate(species="香樟", spec="胸径12cm", quantity=2, unit="株")],
        team.team_id,
        db,
    )
    await PurchaseOrderService.submit_for_approval(order.order_id, team.team_id, db)
    await ApprovalService.approve(order.order_id, user_id, team.team_id, db)
    return user_id, team.team_id, order.order_id


async def test_receipt_created_and_confirmed_updates_order(db):
    """审批生成收货单；填写到货时间后一键确认并更新采购单状态。"""
    _, team_id, _ = await _setup_approved(db)
    receipts = await ReceiptService.list_receipts(team_id, db)
    assert len(receipts) == 1
    receipt = receipts[0]
    supplier_order = await db.get(SupplierOrder, receipt.supplier_order_id)
    supplier_item = supplier_order.items[0]
    supplier_item.supplier_name = "示例园林"
    supplier_item.final_price = 810
    receipt_model = (
        await db.execute(
            select(Receipt).options(selectinload(Receipt.items)).where(Receipt.id == receipt.receipt_id)
        )
    ).scalar_one()
    receipt_item = receipt_model.items[0]
    receipt_item.supplier_name = "示例园林"
    receipt_item.final_price = 810
    db.add(MaterialHistoryRecord(
        team_id=team_id,
        supplier_name="示例园林",
        material_name=receipt_item.species,
        spec=receipt_item.spec,
        unit=receipt_item.unit,
        source_file="quote.csv",
        fingerprint="receipt-history-test",
        final_price=800,
    ))
    await db.flush()
    with pytest.raises(InvalidStatusTransitionError):
        await ReceiptService.confirm_all(receipt.receipt_id, team_id, db)

    arrived_at = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    updated = await ReceiptService.update_receipt(
        receipt.receipt_id,
        ReceiptUpdate(items=[ReceiptItemUpdate(item_id=receipt.items[0].item_id, arrived_at=arrived_at)]),
        team_id,
        db,
    )
    assert updated.status == "pending"
    confirmed = await ReceiptService.confirm_all(receipt.receipt_id, team_id, db)
    assert confirmed.status == "received"
    assert confirmed.items[0].is_received is True
    assert confirmed.items[0].arrived_at.replace(tzinfo=timezone.utc) == arrived_at

    supplier_order = await db.get(SupplierOrder, receipt.supplier_order_id)
    order = await db.get(PurchaseOrder, supplier_order.purchase_order_id)
    assert order is not None
    assert order.status == "received"
    history = await db.scalar(
        select(MaterialHistoryRecord).where(MaterialHistoryRecord.fingerprint == "receipt-history-test")
    )
    assert history.receipt_status == "received"
    assert history.final_price == 810
    assert history.ordered_at is not None
    assert history.arrived_at.replace(tzinfo=timezone.utc) == arrived_at
