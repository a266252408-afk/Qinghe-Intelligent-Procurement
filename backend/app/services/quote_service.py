"""报价单确认、查询与团队隔离服务。"""
from datetime import date

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import OrderNotFoundError, QuoteUploadNotFoundError
from app.models.order import PurchaseItem, PurchaseOrder
from app.models.project import Project
from app.models.quote import InquirySheet, Quote, QuoteItem
from app.models.material_history import QuoteUpload
from app.models.material_history import MaterialHistoryRecord
from app.schemas.quote import QuoteCreateInput, QuoteOut, QuoteItemOut
from app.services.material_history import MaterialHistoryService


class QuoteService:
    """报价单业务服务，不负责文件解析或大模型调用。"""

    @staticmethod
    async def create(
        data: QuoteCreateInput,
        team_id: int,
        db: AsyncSession,
        confirmed_by: int | None = None,
    ) -> QuoteOut:
        """确认并保存供应商报价。"""
        order = await QuoteService._get_order(data.order_id, team_id, db)
        if order is None:
            raise OrderNotFoundError()
        confirmer = confirmed_by or order.creator_id
        upload = await QuoteService._get_upload(data.upload_id, team_id, data.file_path, db)
        quote = Quote(
            order_id=data.order_id,
            supplier_name=data.supplier_name.strip(),
            file_path=upload.file_path if upload else data.file_path,
            parsed_data_json={"original_name": data.original_name},
            quote_date=data.quote_date or date.today(),
        )
        quote.items = [QuoteItem(**item.model_dump()) for item in data.items]
        db.add(quote)
        await db.flush()
        await MaterialHistoryService.save_from_quote(quote, upload, team_id, confirmer, db)
        project_name = await db.scalar(select(Project.name).where(Project.id == order.project_id))
        return QuoteService._to_out(quote, order.project_id, project_name or "")

    @staticmethod
    async def create_inquiry_sheet(
        order_id: int, template_id: str, file_path: str, db: AsyncSession
    ) -> InquirySheet:
        """记录生成的询价单文件；文件生成为 Agent 工具职责，持久化归本服务。"""
        sheet = InquirySheet(order_id=order_id, template_id=template_id, file_path=file_path)
        db.add(sheet)
        await db.flush()
        return sheet

    @staticmethod
    async def register_upload(
        team_id: int, user_id: int, file_path: str, original_name: str, db: AsyncSession
    ) -> QuoteUpload:
        """保存报价上传记录，供后续确认时追踪上传人。"""
        return await MaterialHistoryService.register_upload(
            team_id, user_id, file_path, original_name, db
        )

    @staticmethod
    async def _get_upload(
        upload_id: int | None, team_id: int, file_path: str, db: AsyncSession
    ) -> QuoteUpload | None:
        """校验待确认上传记录属于当前团队和当前文件。"""
        if upload_id is None:
            return None
        stmt = select(QuoteUpload).where(
            QuoteUpload.id == upload_id,
            QuoteUpload.team_id == team_id,
            QuoteUpload.file_path == file_path,
            QuoteUpload.confirmed_by.is_(None),
        )
        upload = (await db.execute(stmt)).scalar_one_or_none()
        if upload is None:
            raise QuoteUploadNotFoundError()
        return upload

    @staticmethod
    async def list_by_order(order_id: int, team_id: int, db: AsyncSession) -> list[QuoteOut]:
        """查询团队内指定采购单的全部已确认报价。"""
        if await QuoteService._get_order(order_id, team_id, db) is None:
            raise OrderNotFoundError()
        stmt = (
            select(Quote, Project.id, Project.name)
            .options(selectinload(Quote.items))
            .join(PurchaseOrder, Quote.order_id == PurchaseOrder.id)
            .join(Project, PurchaseOrder.project_id == Project.id)
            .where(
                Quote.order_id == order_id,
                Project.team_id == team_id,
                Project.is_deleted.is_(False),
            )
        )
        rows = (await db.execute(stmt)).all()
        return [
            QuoteService._to_out(quote, row_project_id, project_name)
            for quote, row_project_id, project_name in rows
        ]

    @staticmethod
    async def list_all(
        team_id: int,
        db: AsyncSession,
        project_id: int | None = None,
        order_id: int | None = None,
    ) -> list[QuoteOut]:
        """按项目或采购单查询当前团队已确认报价。"""
        stmt = (
            select(Quote, Project.id, Project.name)
            .options(selectinload(Quote.items))
            .join(PurchaseOrder, Quote.order_id == PurchaseOrder.id)
            .join(Project, PurchaseOrder.project_id == Project.id)
            .where(Project.team_id == team_id, Project.is_deleted.is_(False))
            .order_by(Quote.created_at.desc())
        )
        if project_id is not None:
            stmt = stmt.where(Project.id == project_id)
        if order_id is not None:
            stmt = stmt.where(Quote.order_id == order_id)
        rows = (await db.execute(stmt)).all()
        return [
            QuoteService._to_out(quote, row_project_id, project_name)
            for quote, row_project_id, project_name in rows
        ]

    @staticmethod
    async def delete(quote_id: int, team_id: int, db: AsyncSession) -> None:
        """删除当前团队报价管理记录，长期材料历史保留。"""
        stmt = (
            select(Quote.id)
            .join(PurchaseOrder, Quote.order_id == PurchaseOrder.id)
            .join(Project, PurchaseOrder.project_id == Project.id)
            .where(
                Quote.id == quote_id,
                Project.team_id == team_id,
                Project.is_deleted.is_(False),
            )
        )
        if await db.scalar(stmt) is None:
            from app.core.exceptions import QuoteNotFoundError
            raise QuoteNotFoundError()
        await db.execute(
            update(MaterialHistoryRecord)
            .where(MaterialHistoryRecord.source_quote_id == quote_id)
            .values(source_quote_id=None)
        )
        # 防御：采购项可能引用本报价的报价项（外键无级联），先解除引用再删
        quote_item_ids = select(QuoteItem.id).where(QuoteItem.quote_id == quote_id)
        await db.execute(
            update(PurchaseItem)
            .where(PurchaseItem.supplier_quote_item_id.in_(quote_item_ids))
            .values(supplier_quote_item_id=None)
        )
        await db.execute(delete(QuoteItem).where(QuoteItem.quote_id == quote_id))
        await db.execute(delete(Quote).where(Quote.id == quote_id))

    @staticmethod
    async def _get_order(order_id: int, team_id: int, db: AsyncSession) -> PurchaseOrder | None:
        stmt = select(PurchaseOrder).join(Project, PurchaseOrder.project_id == Project.id).where(
            PurchaseOrder.id == order_id,
            Project.team_id == team_id,
            Project.is_deleted.is_(False),
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    def _to_out(quote: Quote, project_id: int, project_name: str) -> QuoteOut:
        items = [
            QuoteItemOut(
                quote_item_id=item.id,
                quote_id=item.quote_id,
                species=item.species,
                spec=item.spec,
                unit=item.unit,
                unit_price=float(item.unit_price) if item.unit_price is not None else None,
                final_price=float(item.final_price) if item.final_price is not None else None,
                quantity=float(item.quantity) if item.quantity is not None else None,
                total_price=float(item.total_price) if item.total_price is not None else None,
                delivery_days=item.delivery_days,
                payment_terms=item.payment_terms,
                valid_until=item.valid_until,
            )
            for item in quote.items
        ]
        return QuoteOut(
            quote_id=quote.id,
            order_id=quote.order_id,
            project_id=project_id,
            project_name=project_name,
            supplier_id=quote.supplier_id,
            supplier_name=quote.supplier_name,
            file_path=quote.file_path,
            original_name=(quote.parsed_data_json or {}).get("original_name", ""),
            items=items,
            created_at=quote.created_at,
            quote_date=quote.quote_date,
        )
