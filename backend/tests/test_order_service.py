"""采购单服务测试（含状态机）"""
import pytest
from sqlalchemy import select

from app.services.auth_service import AuthService
from app.services.project_service import ProjectService
from app.services.order_service import PurchaseOrderService
from app.schemas.auth import LoginRequest, TeamCreate
from app.schemas.order import OrderCreate, OrderItemCreate, OrderUpdate
from app.schemas.project import ProjectCreate
from app.core.exceptions import (
    EmptyOrderError,
    InvalidStatusTransitionError,
    MissingSupplierSelectionError,
    OrderNotFoundError,
)
from app.core.security import decode_token
from app.models.approval import ApprovalRecord
from app.models.material_history import MaterialHistoryRecord
from app.models.order import PurchaseOrder
from app.models.quote import InquirySheet, Quote, QuoteItem
from app.services.approval_service import ApprovalService


pytestmark = pytest.mark.asyncio


async def _setup(db):
    token = await AuthService.login_or_register(LoginRequest(username="order_user", password="p"), db)
    uid = decode_token(token.access_token)["user_id"]
    team = await AuthService.create_team(uid, TeamCreate(name="OT"), db)
    project = await ProjectService.create_project(ProjectCreate(name="绿化项目"), uid, team.team_id, db)
    return uid, team.team_id, project.project_id


async def test_create_order_draft(db):
    uid, team_id, pid = await _setup(db)
    out = await PurchaseOrderService.create_order(
        OrderCreate(project_id=pid), uid, team_id, db
    )
    assert out.status == "draft"


async def test_custom_order_name_can_be_updated_only_in_draft(db):
    """采购单名称可创建并修改，提交下单申请后固定。"""
    uid, team_id, pid = await _setup(db)
    order = await PurchaseOrderService.create_order(
        OrderCreate(project_id=pid, name="滨河苗木采购"), uid, team_id, db
    )
    assert order.name == "滨河苗木采购"
    updated = await PurchaseOrderService.update_order(
        order.order_id, OrderUpdate(name="滨河苗木采购-一批"), team_id, db
    )
    assert updated.name == "滨河苗木采购-一批"
    await PurchaseOrderService.save_items(
        order.order_id,
        [OrderItemCreate(species="香樟", quantity=1, unit="株")],
        team_id,
        db,
    )
    await PurchaseOrderService.submit_for_approval(order.order_id, team_id, db)
    with pytest.raises(InvalidStatusTransitionError):
        await PurchaseOrderService.update_order(
            order.order_id, OrderUpdate(name="不应修改"), team_id, db
        )


async def test_save_items(db):
    uid, team_id, pid = await _setup(db)
    order = await PurchaseOrderService.create_order(OrderCreate(project_id=pid), uid, team_id, db)
    items = await PurchaseOrderService.save_items(
        order.order_id,
        [OrderItemCreate(species="香樟", spec="胸径15cm", quantity=10, unit="株")],
        team_id,
        db,
    )
    assert len(items) == 1
    assert items[0].species == "香樟"


async def test_supplier_options_and_final_price_default(db):
    """报价匹配采购项，成交价未填时默认采用供应商报价。"""
    uid, team_id, pid = await _setup(db)
    order = await PurchaseOrderService.create_order(OrderCreate(project_id=pid), uid, team_id, db)
    await PurchaseOrderService.save_items(
        order.order_id,
        [OrderItemCreate(species="香樟", spec="胸径15cm", quantity=2, unit="株")],
        team_id,
        db,
    )
    quote = Quote(order_id=order.order_id, supplier_name="示例园林", file_path="quote.csv")
    quote.items = [QuoteItem(species="香樟", spec="胸径15cm", unit="株", unit_price=880)]
    db.add(quote)
    await db.flush()

    options = await PurchaseOrderService.list_supplier_options(order.order_id, team_id, db)
    option = options[0].suppliers[0]
    assert option.supplier_name == "示例园林"
    assert option.unit_price == 880

    await PurchaseOrderService.save_items(
        order.order_id,
        [OrderItemCreate(
            species="香樟", spec="胸径15cm", quantity=2, unit="株",
            supplier_name=option.supplier_name,
            supplier_quote_item_id=option.quote_item_id,
            supplier_quote_price=option.unit_price,
        )],
        team_id,
        db,
    )
    out = await PurchaseOrderService.submit_for_approval(order.order_id, team_id, db)
    assert out.status == "pending_approval"
    assert out.items[0].final_price == 880


async def test_submit_with_quote_requires_supplier_selection(db):
    """存在匹配报价时，未选择供应商不能提交下单申请。"""
    uid, team_id, pid = await _setup(db)
    order = await PurchaseOrderService.create_order(OrderCreate(project_id=pid), uid, team_id, db)
    await PurchaseOrderService.save_items(
        order.order_id,
        [OrderItemCreate(species="香樟", spec="胸径15cm", quantity=2, unit="株")],
        team_id,
        db,
    )
    quote = Quote(order_id=order.order_id, supplier_name="示例园林", file_path="quote.csv")
    quote.items = [QuoteItem(species="香樟", spec="胸径15cm", unit="株", unit_price=880)]
    db.add(quote)
    await db.flush()

    with pytest.raises(MissingSupplierSelectionError):
        await PurchaseOrderService.submit_for_approval(order.order_id, team_id, db)


async def test_submit_for_approval(db):
    uid, team_id, pid = await _setup(db)
    order = await PurchaseOrderService.create_order(OrderCreate(project_id=pid), uid, team_id, db)
    await PurchaseOrderService.save_items(
        order.order_id,
        [OrderItemCreate(species="红枫", spec="高1.5m", quantity=5, unit="棵")],
        team_id, db,
    )
    out = await PurchaseOrderService.submit_for_approval(order.order_id, team_id, db)
    assert out.status == "pending_approval"


async def test_submit_empty_order_raises(db):
    uid, team_id, pid = await _setup(db)
    order = await PurchaseOrderService.create_order(OrderCreate(project_id=pid), uid, team_id, db)
    with pytest.raises(EmptyOrderError):
        await PurchaseOrderService.submit_for_approval(order.order_id, team_id, db)


async def test_invalid_transition_raises(db):
    uid, team_id, pid = await _setup(db)
    order = await PurchaseOrderService.create_order(OrderCreate(project_id=pid), uid, team_id, db)
    # draft 不能直接跳 ordered
    with pytest.raises(InvalidStatusTransitionError):
        await PurchaseOrderService.update_status(order.order_id, "ordered", team_id, db)


async def test_full_state_machine(db):
    """测试完整流转：draft→pending→approved→ordered→received→settled"""
    uid, team_id, pid = await _setup(db)
    order = await PurchaseOrderService.create_order(OrderCreate(project_id=pid), uid, team_id, db)
    await PurchaseOrderService.save_items(
        order.order_id,
        [OrderItemCreate(species="桂花", spec="高2m", quantity=3, unit="棵")],
        team_id, db,
    )
    oid = order.order_id
    await PurchaseOrderService.submit_for_approval(oid, team_id, db)
    await PurchaseOrderService.update_status(oid, "approved", team_id, db)
    await PurchaseOrderService.update_status(oid, "ordered", team_id, db)
    await PurchaseOrderService.confirm_receipt(oid, team_id, db)
    final = await PurchaseOrderService.update_status(oid, "settled", team_id, db)
    assert final.status == "settled"


async def test_cross_team_order_not_found(db):
    uid, team_id, pid = await _setup(db)
    order = await PurchaseOrderService.create_order(OrderCreate(project_id=pid), uid, team_id, db)
    with pytest.raises(OrderNotFoundError):
        await PurchaseOrderService.get_order(order.order_id, team_id + 999, db)


async def test_delete_order_cleans_management_records_and_keeps_history(db):
    """删除采购单不跨团队，并清理报价管理记录但保留长期历史。"""
    uid, team_id, pid = await _setup(db)
    order = await PurchaseOrderService.create_order(OrderCreate(project_id=pid), uid, team_id, db)
    db.add(InquirySheet(order_id=order.order_id, template_id="default", file_path="inquiry.xlsx"))
    quote = Quote(order_id=order.order_id, supplier_name="供应商", file_path="quote.xlsx")
    quote.items = [QuoteItem(species="香樟", spec="胸径12cm", unit="株")]
    db.add(quote)
    await db.flush()
    history = MaterialHistoryRecord(
        team_id=team_id,
        supplier_name="供应商",
        material_name="香樟",
        spec="胸径12cm",
        unit="株",
        source_file="quote.xlsx",
        source_quote_id=quote.id,
        fingerprint="delete-order-history",
    )
    db.add(history)
    await db.flush()

    await PurchaseOrderService.delete_order(order.order_id, team_id, db)

    assert await db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order.order_id)) is None
    assert await db.scalar(select(Quote).where(Quote.id == quote.id)) is None
    assert await db.scalar(select(QuoteItem).where(QuoteItem.quote_id == quote.id)) is None
    assert await db.scalar(select(InquirySheet).where(InquirySheet.order_id == order.order_id)) is None
    assert (await db.get(MaterialHistoryRecord, history.id)).source_quote_id is None


async def test_delete_order_with_approval_records(db):
    """审批过的采购单删除时同步清理审批与下单记录，不触发外键违例。"""
    uid, team_id, pid = await _setup(db)
    order = await PurchaseOrderService.create_order(OrderCreate(project_id=pid), uid, team_id, db)
    await PurchaseOrderService.save_items(
        order.order_id,
        [OrderItemCreate(species="香樟", spec="胸径15cm", quantity=2, unit="株")],
        team_id, db,
    )
    await PurchaseOrderService.submit_for_approval(order.order_id, team_id, db)
    await ApprovalService.approve(order.order_id, uid, team_id, db, role="owner")

    await PurchaseOrderService.delete_order(order.order_id, team_id, db)
    await db.flush()

    assert await db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order.order_id)) is None
    assert await db.scalar(
        select(ApprovalRecord).where(ApprovalRecord.order_id == order.order_id)
    ) is None
