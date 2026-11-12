"""下单管理查询与文件导出服务。"""
import asyncio
import csv
from io import BytesIO, StringIO

import openpyxl
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from datetime import datetime, timezone

from app.core.exceptions import OrderNotFoundError, UnsupportedFormatError
from app.models.supplier_order import SupplierOrderItem
from app.models.supplier_order import SupplierOrder
from app.models.receipt import Receipt, ReceiptItem
from app.models.order import PurchaseOrder
from app.models.project import Project
from app.services.order_service import PurchaseOrderService


class SupplierOrderService:
    """提供下单记录导出能力，业务数据由采购单服务创建。"""

    @staticmethod
    async def delete(supplier_order_id: int, team_id: int, db: AsyncSession) -> None:
        """删除团队下单记录及收货单，保留采购单和长期历史。"""
        stmt = (
            select(SupplierOrder)
            .join(PurchaseOrder, SupplierOrder.purchase_order_id == PurchaseOrder.id)
            .join(Project, PurchaseOrder.project_id == Project.id)
            .where(
                SupplierOrder.id == supplier_order_id,
                SupplierOrder.team_id == team_id,
                Project.team_id == team_id,
            )
        )
        order = (await db.execute(stmt)).scalar_one_or_none()
        if order is None:
            raise OrderNotFoundError("下单记录不存在")
        receipt_ids = select(Receipt.id).where(Receipt.supplier_order_id == order.id)
        await db.execute(delete(ReceiptItem).where(ReceiptItem.receipt_id.in_(receipt_ids)))
        await db.execute(delete(Receipt).where(Receipt.supplier_order_id == order.id))
        await db.execute(delete(SupplierOrderItem).where(SupplierOrderItem.supplier_order_id == order.id))
        await db.execute(delete(SupplierOrder).where(SupplierOrder.id == order.id))
        purchase_order = await db.get(PurchaseOrder, order.purchase_order_id)
        if purchase_order and purchase_order.status in {"ordered", "received"}:
            purchase_order.status = "approved"
            purchase_order.updated_at = datetime.now(timezone.utc)

    @staticmethod
    async def export(
        supplier_order_id: int,
        team_id: int,
        file_format: str,
        db: AsyncSession,
        item_id: int | None = None,
    ) -> StreamingResponse:
        """导出整单或单个下单项为 CSV/Excel。"""
        order = await PurchaseOrderService.get_supplier_order(supplier_order_id, team_id, db)
        if file_format not in {"csv", "xlsx"}:
            raise UnsupportedFormatError("仅支持 csv 或 xlsx 格式")
        items = [item for item in order.items if item_id is None or item.item_id == item_id]
        if not items:
            raise OrderNotFoundError("下单明细不存在")
        filename = f"supplier_order_{supplier_order_id}"
        if item_id is not None:
            filename += f"_item_{item_id}"
        if file_format == "csv":
            return _csv_response(items, f"{filename}.csv")
        # openpyxl 生成 Excel 是同步 CPU 操作，放线程池避免阻塞事件循环
        return await asyncio.to_thread(_xlsx_response, items, f"{filename}.xlsx")


def _headers() -> list[str]:
    return ["品种", "规格", "数量", "单位", "供应商", "供应商报价", "成交价", "总价"]


def _values(item: SupplierOrderItem) -> list[object]:
    return [
        item.species,
        item.spec,
        item.quantity,
        item.unit,
        item.supplier_name or "",
        item.supplier_quote_price,
        item.final_price,
        item.total_price,
    ]


def _csv_response(items: list, filename: str) -> StreamingResponse:
    """构造 UTF-8 BOM CSV 下载响应。"""
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_headers())
    for item in items:
        writer.writerow(_values(item))
    return StreamingResponse(
        iter([buffer.getvalue().encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _xlsx_response(items: list, filename: str) -> StreamingResponse:
    """构造 Excel 下载响应。"""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "下单表"
    sheet.append(_headers())
    for item in items:
        sheet.append(_values(item))
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
