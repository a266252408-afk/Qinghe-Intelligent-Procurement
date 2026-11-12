"""收货单生成、维护与确认服务。"""
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import InvalidStatusTransitionError, OrderNotFoundError
from app.models.order import PurchaseOrder
from app.models.project import Project
from app.models.receipt import Receipt, ReceiptItem
from app.models.supplier_order import SupplierOrder
from app.schemas.receipt import ReceiptItemOut, ReceiptOut, ReceiptUpdate


class ReceiptService:
    """管理团队收货单及其材料确认状态。"""

    @staticmethod
    async def create_for_supplier_order(
        supplier_order_id: int, team_id: int, db: AsyncSession
    ) -> ReceiptOut:
        """下单审批通过时创建收货单，重复调用保持幂等。"""
        supplier_order, project_id, project_name = await _load_supplier_order(
            supplier_order_id, team_id, db
        )
        existing = await db.scalar(
            select(Receipt).where(Receipt.supplier_order_id == supplier_order_id)
        )
        if existing:
            return await _receipt_out(existing, project_id, project_name)
        receipt = Receipt(supplier_order_id=supplier_order_id, team_id=team_id, status="pending")
        receipt.items = [
            ReceiptItem(
                supplier_order_item_id=item.id,
                species=item.species,
                spec=item.spec,
                quantity=item.quantity,
                unit=item.unit,
                supplier_name=item.supplier_name,
                final_price=item.final_price,
            )
            for item in supplier_order.items
        ]
        db.add(receipt)
        await db.flush()
        return await _receipt_out(receipt, project_id, project_name)

    @staticmethod
    async def list_receipts(team_id: int, db: AsyncSession) -> list[ReceiptOut]:
        """查询当前团队全部收货单。"""
        stmt = (
            select(Receipt, Project.id, Project.name)
            .options(selectinload(Receipt.items))
            .join(SupplierOrder, Receipt.supplier_order_id == SupplierOrder.id)
            .join(PurchaseOrder, SupplierOrder.purchase_order_id == PurchaseOrder.id)
            .join(Project, PurchaseOrder.project_id == Project.id)
            .where(Receipt.team_id == team_id, Project.is_deleted.is_(False))
            .order_by(Receipt.created_at.desc())
        )
        rows = (await db.execute(stmt)).all()
        return [await _receipt_out(receipt, pid, name) for receipt, pid, name in rows]

    @staticmethod
    async def get_receipt(receipt_id: int, team_id: int, db: AsyncSession) -> ReceiptOut:
        """查询收货单详情并校验团队归属。"""
        receipt, pid, name = await _load_receipt(receipt_id, team_id, db)
        return await _receipt_out(receipt, pid, name)

    @staticmethod
    async def delete(receipt_id: int, team_id: int, db: AsyncSession) -> None:
        """删除团队收货单及其明细，不删除下单快照和长期历史。"""
        receipt, _, _ = await _load_receipt(receipt_id, team_id, db)
        await db.execute(delete(ReceiptItem).where(ReceiptItem.receipt_id == receipt.id))
        await db.execute(delete(Receipt).where(Receipt.id == receipt.id, Receipt.team_id == team_id))

    @staticmethod
    async def update_receipt(
        receipt_id: int, data: ReceiptUpdate, team_id: int, db: AsyncSession
    ) -> ReceiptOut:
        """保存人工填写的到货时间和逐项确认状态。"""
        receipt, pid, name = await _load_receipt(receipt_id, team_id, db)
        items = {item.id: item for item in receipt.items}
        for update in data.items:
            item = items.get(update.item_id)
            if item is None:
                raise OrderNotFoundError("收货明细不存在")
            if update.is_received and update.arrived_at is None and item.arrived_at is None:
                raise InvalidStatusTransitionError("确认收货前请填写到货时间")
            item.arrived_at = update.arrived_at or item.arrived_at
            item.is_received = update.is_received
        await _finish_receipt_if_complete(receipt, db)
        await db.flush()
        return await _receipt_out(receipt, pid, name)

    @staticmethod
    async def confirm_all(receipt_id: int, team_id: int, db: AsyncSession) -> ReceiptOut:
        """一键确认全部收货，要求每项均已填写到货时间。"""
        receipt, pid, name = await _load_receipt(receipt_id, team_id, db)
        if any(item.arrived_at is None for item in receipt.items):
            raise InvalidStatusTransitionError("请先填写所有材料的到货时间")
        for item in receipt.items:
            item.is_received = True
        await _finish_receipt_if_complete(receipt, db)
        await db.flush()
        return await _receipt_out(receipt, pid, name)


async def _load_supplier_order(supplier_order_id: int, team_id: int, db: AsyncSession):
    """加载团队下单记录及项目名称。"""
    stmt = (
        select(SupplierOrder, Project.id, Project.name)
        .options(selectinload(SupplierOrder.items))
        .join(PurchaseOrder, SupplierOrder.purchase_order_id == PurchaseOrder.id)
        .join(Project, PurchaseOrder.project_id == Project.id)
        .where(SupplierOrder.id == supplier_order_id, SupplierOrder.team_id == team_id)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise OrderNotFoundError("下单记录不存在")
    return row


async def _load_receipt(receipt_id: int, team_id: int, db: AsyncSession):
    """加载团队收货单及项目名称。"""
    stmt = (
        select(Receipt, Project.id, Project.name)
        .options(selectinload(Receipt.items))
        .join(SupplierOrder, Receipt.supplier_order_id == SupplierOrder.id)
        .join(PurchaseOrder, SupplierOrder.purchase_order_id == PurchaseOrder.id)
        .join(Project, PurchaseOrder.project_id == Project.id)
        .where(Receipt.id == receipt_id, Receipt.team_id == team_id)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise OrderNotFoundError("收货单不存在")
    return row


async def _finish_receipt_if_complete(receipt: Receipt, db: AsyncSession) -> None:
    """收货明细全部确认后同步采购单状态。"""
    if not receipt.items or not all(item.is_received for item in receipt.items):
        receipt.status = "partial" if any(item.is_received for item in receipt.items) else "pending"
        return
    receipt.status = "received"
    receipt.confirmed_at = datetime.now(timezone.utc)
    from app.services.material_history import MaterialHistoryService
    await MaterialHistoryService.update_from_receipt(receipt, receipt.team_id, db)
    supplier_order = await db.get(SupplierOrder, receipt.supplier_order_id)
    if supplier_order:
        supplier_order.status = "received"
        purchase_order = await db.get(PurchaseOrder, supplier_order.purchase_order_id)
        if purchase_order:
            purchase_order.status = "received"
            purchase_order.updated_at = datetime.now(timezone.utc)


async def _receipt_out(receipt: Receipt, project_id: int, project_name: str) -> ReceiptOut:
    """构造收货单响应。"""
    return ReceiptOut(
        receipt_id=receipt.id,
        supplier_order_id=receipt.supplier_order_id,
        project_id=project_id,
        project_name=project_name,
        status=receipt.status,
        confirmed_at=receipt.confirmed_at,
        items=[
            ReceiptItemOut(
                item_id=item.id,
                receipt_id=item.receipt_id,
                supplier_order_item_id=item.supplier_order_item_id,
                species=item.species,
                spec=item.spec,
                quantity=float(item.quantity),
                unit=item.unit,
                supplier_name=item.supplier_name,
                final_price=float(item.final_price) if item.final_price is not None else None,
                arrived_at=item.arrived_at,
                is_received=item.is_received,
            )
            for item in receipt.items
        ],
    )
