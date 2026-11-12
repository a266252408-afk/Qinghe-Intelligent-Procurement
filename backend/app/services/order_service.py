"""采购单管理服务
依据：docs/module-sdd/order_service.md
"""
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    EmptyOrderError,
    InvalidStatusTransitionError,
    MissingSupplierSelectionError,
    OrderNotFoundError,
)
from app.models.approval import ApprovalRecord
from app.models.order import PurchaseItem, PurchaseOrder
from app.models.project import Project
from app.models.material_history import MaterialHistoryRecord
from app.models.quote import InquirySheet, Quote, QuoteItem
from app.models.supplier_order import SupplierOrder, SupplierOrderItem
from app.schemas.supplier_order import SupplierOrderOut, SupplierOrderItemOut
from app.schemas.order import (
    OrderCreate,
    OrderItemCreate,
    OrderItemOut,
    OrderListOut,
    OrderOut,
    OrderUpdate,
    OrderSupplierOptionsOut,
    SupplierOption,
)

# 合法状态转换表
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft":            {"pending_approval"},
    "pending_approval": {"approved", "rejected"},
    "approved":         {"ordered"},
    "ordered":          {"received"},
    "received":         {"settled"},
    "rejected":         {"draft"},
    "settled":          set(),
}


def _item_to_out(item: PurchaseItem) -> OrderItemOut:
    return OrderItemOut(
        item_id=item.id,
        order_id=item.order_id,
        species=item.species,
        spec=item.spec,
        quantity=float(item.quantity),
        unit=item.unit,
        unit_price=float(item.unit_price) if item.unit_price is not None else None,
        total_price=float(item.total_price) if item.total_price is not None else None,
        supplier_name=item.supplier_name,
        supplier_quote_item_id=item.supplier_quote_item_id,
        supplier_quote_price=(
            float(item.supplier_quote_price) if item.supplier_quote_price is not None else None
        ),
        final_price=float(item.final_price) if item.final_price is not None else None,
    )


def _order_to_out(order: PurchaseOrder, project_name: str = "") -> OrderOut:
    return OrderOut(
        order_id=order.id,
        project_id=order.project_id,
        project_name=project_name,
        name=order.name,
        creator_id=order.creator_id,
        status=order.status,
        total_amount=float(order.total_amount) if order.total_amount is not None else None,
        remark=order.remark,
        items=[_item_to_out(i) for i in (order.items or [])],
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


async def _get_order_with_team(
    order_id: int, team_id: int, db: AsyncSession
) -> tuple[PurchaseOrder, str]:
    """加载采购单并校验 team_id（通过 project 链路）"""
    stmt = (
        select(PurchaseOrder, Project.name)
        .options(selectinload(PurchaseOrder.items))
        .join(Project, PurchaseOrder.project_id == Project.id)
        .where(PurchaseOrder.id == order_id, Project.team_id == team_id)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise OrderNotFoundError()
    return row[0], row[1]


class PurchaseOrderService:

    @staticmethod
    async def create_order(
        data: OrderCreate, creator_id: int, team_id: int, db: AsyncSession
    ) -> OrderOut:
        """创建采购单，初始状态 draft"""
        # 校验 project 属于该团队
        project = await db.get(Project, data.project_id)
        if project is None or project.team_id != team_id or project.is_deleted:
            from app.core.exceptions import ProjectNotFoundError
            raise ProjectNotFoundError()

        order = PurchaseOrder(
            project_id=data.project_id,
            creator_id=creator_id,
            status="draft",
            name=data.name.strip() if data.name and data.name.strip() else None,
            remark=data.remark,
        )
        db.add(order)
        await db.flush()
        # 新建订单无采购项，直接构造输出（避免触发懒加载）
        return OrderOut(
            order_id=order.id,
            project_id=order.project_id,
            project_name=project.name,
            creator_id=order.creator_id,
            name=order.name,
            status=order.status,
            total_amount=None,
            remark=order.remark,
            items=[],
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

    @staticmethod
    async def get_order(order_id: int, team_id: int, db: AsyncSession) -> OrderOut:
        """查询采购单详情（含采购项）"""
        order, project_name = await _get_order_with_team(order_id, team_id, db)
        return _order_to_out(order, project_name)

    @staticmethod
    async def update_order(
        order_id: int, data: OrderUpdate, team_id: int, db: AsyncSession
    ) -> OrderOut:
        """更新草稿采购单的自定义名称和备注。"""
        order, project_name = await _get_order_with_team(order_id, team_id, db)
        if order.status != "draft":
            raise InvalidStatusTransitionError("只有草稿采购单可以修改名称或备注")
        if data.name is not None:
            order.name = data.name.strip() or None
        if data.remark is not None:
            order.remark = data.remark.strip() or None
        order.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return _order_to_out(order, project_name)

    @staticmethod
    async def list_orders(
        team_id: int,
        project_id: int | None,
        status: str | None,
        creator_id: int | None,
        db: AsyncSession,
    ) -> OrderListOut:
        """查询采购单列表"""
        stmt = (
            select(PurchaseOrder, Project.name)
            .options(selectinload(PurchaseOrder.items))
            .join(Project, PurchaseOrder.project_id == Project.id)
            .where(Project.team_id == team_id, Project.is_deleted.is_(False))
            .order_by(PurchaseOrder.updated_at.desc())
        )
        if project_id:
            stmt = stmt.where(PurchaseOrder.project_id == project_id)
        if status:
            stmt = stmt.where(PurchaseOrder.status == status)
        if creator_id:
            stmt = stmt.where(PurchaseOrder.creator_id == creator_id)

        rows = (await db.execute(stmt)).all()
        return OrderListOut(total=len(rows), items=[_order_to_out(o, name) for o, name in rows])

    @staticmethod
    async def save_items(
        order_id: int,
        items: list[OrderItemCreate],
        team_id: int,
        db: AsyncSession,
    ) -> list[OrderItemOut]:
        """覆盖保存采购项：先删旧，再批量插入"""
        order, _ = await _get_order_with_team(order_id, team_id, db)  # 校验归属
        if order.status != "draft":
            raise InvalidStatusTransitionError("只有草稿采购单可以修改采购项")

        await db.execute(delete(PurchaseItem).where(PurchaseItem.order_id == order_id))

        new_items: list[PurchaseItem] = []
        for it in items:
            row = PurchaseItem(
                order_id=order_id,
                species=it.species,
                spec=it.spec,
                quantity=it.quantity,
                unit=it.unit,
                unit_price=it.unit_price,
                total_price=it.total_price,
                supplier_name=it.supplier_name,
                supplier_quote_item_id=it.supplier_quote_item_id,
                supplier_quote_price=it.supplier_quote_price,
                final_price=(
                    it.final_price
                    if it.final_price is not None
                    else it.supplier_quote_price
                ),
            )
            db.add(row)
            new_items.append(row)
        await db.flush()
        return [_item_to_out(r) for r in new_items]

    @staticmethod
    async def submit_for_approval(order_id: int, team_id: int, db: AsyncSession) -> OrderOut:
        """提交下单审批：draft → pending_approval"""
        order, project_name = await _get_order_with_team(order_id, team_id, db)
        if not order.items:
            raise EmptyOrderError()
        await _validate_supplier_selection(order, team_id, db)
        _assert_transition(order.status, "pending_approval")
        order.status = "pending_approval"
        order.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return _order_to_out(order, project_name)

    @staticmethod
    async def list_supplier_options(
        order_id: int, team_id: int, db: AsyncSession
    ) -> list[OrderSupplierOptionsOut]:
        """返回采购单每项材料匹配到的团队报价供应商。"""
        order, _ = await _get_order_with_team(order_id, team_id, db)
        stmt = (
            select(Quote)
            .options(selectinload(Quote.items))
            .join(PurchaseOrder, Quote.order_id == PurchaseOrder.id)
            .join(Project, PurchaseOrder.project_id == Project.id)
            .where(Quote.order_id == order_id, Project.team_id == team_id)
        )
        quotes = (await db.execute(stmt)).scalars().unique().all()
        result = []
        for item in order.items:
            options = [
                SupplierOption(
                    quote_id=quote.id,
                    quote_item_id=quote_item.id,
                    supplier_name=quote.supplier_name or "未命名供应商",
                    unit_price=float(quote_item.unit_price)
                    if quote_item.unit_price is not None else None,
                )
                for quote in quotes
                for quote_item in quote.items
                if _same_material(item, quote_item)
            ]
            result.append(OrderSupplierOptionsOut(
                item_id=item.id,
                species=item.species,
                spec=item.spec,
                unit=item.unit,
                suppliers=options,
            ))
        return result

    @staticmethod
    async def update_status(
        order_id: int, new_status: str, team_id: int, db: AsyncSession
    ) -> OrderOut:
        """通用状态更新，校验合法转换"""
        order, project_name = await _get_order_with_team(order_id, team_id, db)
        _assert_transition(order.status, new_status)
        order.status = new_status
        order.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return _order_to_out(order, project_name)

    @staticmethod
    async def get_order_scoped(order_id: int, team_id: int, db: AsyncSession) -> PurchaseOrder:
        """加载采购单（含明细）并校验团队归属；供 Agent 层读取输入使用。"""
        order, _ = await _get_order_with_team(order_id, team_id, db)
        return order

    @staticmethod
    async def get_order_with_project_scoped(
        order_id: int, team_id: int, db: AsyncSession
    ) -> tuple[PurchaseOrder, str]:
        """加载采购单（含明细）与所属项目名称并校验团队归属；供需要项目名的 Agent 使用。"""
        return await _get_order_with_team(order_id, team_id, db)

    @staticmethod
    async def list_quotes_for_order(order_id: int, team_id: int, db: AsyncSession) -> list[Quote]:
        """加载某采购单的全部报价（含报价项），团队校验走项目链路；供比价输入使用。"""
        stmt = (
            select(Quote)
            .options(selectinload(Quote.items))
            .join(PurchaseOrder, Quote.order_id == PurchaseOrder.id)
            .join(Project, PurchaseOrder.project_id == Project.id)
            .where(Quote.order_id == order_id, Project.team_id == team_id)
        )
        return list((await db.execute(stmt)).scalars().unique().all())

    @staticmethod
    async def confirm_receipt(order_id: int, team_id: int, db: AsyncSession) -> OrderOut:
        """确认收货：ordered → received"""
        return await PurchaseOrderService.update_status(order_id, "received", team_id, db)

    @staticmethod
    async def delete_order(order_id: int, team_id: int, db: AsyncSession) -> None:
        """删除当前团队采购单及其询价、报价记录，长期历史报价保留。"""
        order, _ = await _get_order_with_team(order_id, team_id, db)
        quote_ids = select(Quote.id).where(Quote.order_id == order.id)
        await db.execute(
            update(MaterialHistoryRecord)
            .where(MaterialHistoryRecord.source_quote_id.in_(quote_ids))
            .values(source_quote_id=None)
        )
        await db.execute(delete(InquirySheet).where(InquirySheet.order_id == order.id))
        await db.execute(delete(ApprovalRecord).where(ApprovalRecord.order_id == order.id))
        # 防御：其他采购项若引用本单报价项（外键无级联），先解除引用再删报价
        quote_item_ids = select(QuoteItem.id).where(QuoteItem.quote_id.in_(quote_ids))
        await db.execute(
            update(PurchaseItem)
            .where(PurchaseItem.supplier_quote_item_id.in_(quote_item_ids))
            .values(supplier_quote_item_id=None)
        )
        await db.execute(delete(QuoteItem).where(QuoteItem.quote_id.in_(quote_ids)))
        await db.execute(delete(Quote).where(Quote.order_id == order.id))
        await db.execute(delete(PurchaseItem).where(PurchaseItem.order_id == order.id))
        await db.execute(delete(PurchaseOrder).where(PurchaseOrder.id == order.id))

    @staticmethod
    async def create_supplier_order(
        order_id: int, team_id: int, db: AsyncSession
    ) -> SupplierOrderOut:
        """管理员审批通过后创建下单快照，记录下单时间。"""
        order, project_name = await _get_order_with_team(order_id, team_id, db)
        if order.status != "approved":
            raise InvalidStatusTransitionError("只有审批通过的下单申请可以生成下单记录")
        existing = await db.scalar(
            select(SupplierOrder).where(
                SupplierOrder.purchase_order_id == order_id,
                SupplierOrder.team_id == team_id,
            )
        )
        if existing:
            from app.services.receipt_service import ReceiptService
            await ReceiptService.create_for_supplier_order(existing.id, team_id, db)
            return await _supplier_order_out(existing, project_name, order.project_id, db, order.name)
        now = datetime.now(timezone.utc)
        supplier_order = SupplierOrder(
            purchase_order_id=order_id,
            team_id=team_id,
            status="ordered",
            ordered_at=now,
        )
        supplier_order.items = [
            SupplierOrderItem(
                purchase_item_id=item.id,
                species=item.species,
                spec=item.spec,
                quantity=item.quantity,
                unit=item.unit,
                supplier_name=item.supplier_name,
                supplier_quote_price=item.supplier_quote_price,
                final_price=item.final_price,
                total_price=(
                    item.quantity * item.final_price
                    if item.final_price is not None else item.total_price
                ),
            )
            for item in order.items
        ]
        db.add(supplier_order)
        order.status = "ordered"
        order.updated_at = now
        await db.flush()
        from app.services.receipt_service import ReceiptService
        await ReceiptService.create_for_supplier_order(supplier_order.id, team_id, db)
        return await _supplier_order_out(supplier_order, project_name, order.project_id, db, order.name)

    @staticmethod
    async def list_supplier_orders(
        team_id: int, db: AsyncSession, project_id: int | None = None
    ) -> list[SupplierOrderOut]:
        """查询当前团队下单管理记录。"""
        stmt = (
            select(SupplierOrder, Project.id, Project.name, PurchaseOrder.name)
            .options(selectinload(SupplierOrder.items))
            .join(PurchaseOrder, SupplierOrder.purchase_order_id == PurchaseOrder.id)
            .join(Project, PurchaseOrder.project_id == Project.id)
            .where(SupplierOrder.team_id == team_id, Project.is_deleted.is_(False))
            .order_by(SupplierOrder.ordered_at.desc())
        )
        if project_id is not None:
            stmt = stmt.where(Project.id == project_id)
        rows = (await db.execute(stmt)).all()
        return [await _supplier_order_out(item, name, pid, db, order_name) for item, pid, name, order_name in rows]

    @staticmethod
    async def get_supplier_order(
        supplier_order_id: int, team_id: int, db: AsyncSession
    ) -> SupplierOrderOut:
        """查询下单记录详情。"""
        stmt = (
            select(SupplierOrder, Project.id, Project.name, PurchaseOrder.name)
            .options(selectinload(SupplierOrder.items))
            .join(PurchaseOrder, SupplierOrder.purchase_order_id == PurchaseOrder.id)
            .join(Project, PurchaseOrder.project_id == Project.id)
            .where(SupplierOrder.id == supplier_order_id, SupplierOrder.team_id == team_id)
        )
        row = (await db.execute(stmt)).first()
        if row is None:
            raise OrderNotFoundError("下单记录不存在")
        return await _supplier_order_out(row[0], row[2], row[1], db, row[3])


def _assert_transition(current: str, target: str) -> None:
    """断言状态转换合法，否则抛出异常"""
    if target not in _VALID_TRANSITIONS.get(current, set()):
        raise InvalidStatusTransitionError(
            f"不允许从 {current} 转换到 {target}"
        )


def _same_material(purchase_item: PurchaseItem, quote_item: QuoteItem) -> bool:
    """按品种、规格和单位匹配采购项与供应商报价项。"""
    return (
        purchase_item.species.strip() == quote_item.species.strip()
        and purchase_item.spec.strip() == quote_item.spec.strip()
        and purchase_item.unit.strip() == quote_item.unit.strip()
    )


async def _validate_supplier_selection(
    order: PurchaseOrder, team_id: int, db: AsyncSession
) -> None:
    """有可用报价时，提交下单申请必须逐项完成供应商和成交价选择。"""
    options = await PurchaseOrderService.list_supplier_options(order.id, team_id, db)
    options_by_item = {item.item_id: item.suppliers for item in options}
    if any(options_by_item.values()):
        for item in order.items:
            item_options = options_by_item.get(item.id, [])
            valid_ids = {option.quote_item_id for option in item_options}
            if (
                item.supplier_quote_item_id not in valid_ids
                or not item.supplier_name
                or item.final_price is None
            ):
                raise MissingSupplierSelectionError()


async def _supplier_order_out(
    supplier_order: SupplierOrder,
    project_name: str,
    project_id: int,
    db: AsyncSession,
    purchase_order_name: str | None = None,
) -> SupplierOrderOut:
    """构造下单记录输出。"""
    return SupplierOrderOut(
        supplier_order_id=supplier_order.id,
        purchase_order_id=supplier_order.purchase_order_id,
        project_id=project_id,
        project_name=project_name,
        purchase_order_name=purchase_order_name,
        status=supplier_order.status,
        ordered_at=supplier_order.ordered_at,
        items=[
            SupplierOrderItemOut(
                item_id=item.id,
                supplier_order_id=item.supplier_order_id,
                purchase_item_id=item.purchase_item_id,
                species=item.species,
                spec=item.spec,
                quantity=float(item.quantity),
                unit=item.unit,
                supplier_name=item.supplier_name,
                supplier_quote_price=(
                    float(item.supplier_quote_price)
                    if item.supplier_quote_price is not None else None
                ),
                final_price=float(item.final_price) if item.final_price is not None else None,
                total_price=float(item.total_price) if item.total_price is not None else None,
            )
            for item in supplier_order.items
        ],
    )
