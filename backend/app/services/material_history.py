"""长期材料历史记录服务：团队隔离、去重、查询和向量索引。"""
import hashlib
import json
import logging
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.material_history import MaterialHistoryRecord, QuoteUpload
from app.models.order import PurchaseOrder
from app.models.project import Project
from app.models.quote import Quote
from app.models.receipt import Receipt
from app.models.supplier_order import SupplierOrder
from app.schemas.material_history import MaterialHistoryFilter, MaterialHistoryOut

logger = logging.getLogger(__name__)


class MaterialHistoryService:
    """管理长期供应商材料报价历史。"""

    @staticmethod
    async def search_for_chat(
        material_name: str,
        team_id: int,
        db: AsyncSession,
    ) -> list[MaterialHistoryOut]:
        """按材料名称查询当前团队长期记忆，供对话工具调用。"""
        name = material_name.strip()
        if not name:
            return []
        return await MaterialHistoryService.list_records(
            MaterialHistoryFilter(material_name=name), team_id, db
        )

    @staticmethod
    async def suggest_suppliers(
        keyword: str,
        team_id: int,
        db: AsyncSession,
    ) -> list[str]:
        """按关键词模糊匹配团队内已存在的供应商名，供查询空结果时给出换字段指引。

        只做存在性匹配、不返回记录本体，把"是否换字段"的决策留给模型。
        """
        name = keyword.strip()
        if not name:
            return []
        rows = await db.execute(
            select(MaterialHistoryRecord.supplier_name)
            .where(
                MaterialHistoryRecord.team_id == team_id,
                MaterialHistoryRecord.supplier_name.contains(name),
            )
            .distinct()
            .limit(3)
        )
        return [value for (value,) in rows.all() if value]

    @staticmethod
    async def register_upload(
        team_id: int,
        user_id: int,
        file_path: str,
        original_name: str,
        db: AsyncSession,
    ) -> QuoteUpload:
        """记录报价文件上传人，返回待确认上传记录。"""
        upload = QuoteUpload(
            team_id=team_id,
            uploaded_by=user_id,
            file_path=file_path,
            original_name=original_name,
        )
        db.add(upload)
        await db.flush()
        return upload

    @staticmethod
    async def save_from_quote(
        quote: Quote,
        upload: QuoteUpload | None,
        team_id: int,
        confirmed_by: int,
        db: AsyncSession,
    ) -> int:
        """将确认后的报价明细写入长期记忆，返回新增条数。"""
        upload_user = upload.uploaded_by if upload else confirmed_by
        source_file = upload.file_path if upload else quote.file_path
        quote_date = quote.quote_date or datetime.now(timezone.utc).date()
        project_id = await _resolve_project_id(quote.order_id, db)
        created = 0
        for item in quote.items:
            record = _build_record(
                quote, item, team_id, quote_date, source_file, upload_user, confirmed_by,
                project_id,
            )
            exists = await db.scalar(
                select(MaterialHistoryRecord.id).where(
                    MaterialHistoryRecord.team_id == team_id,
                    MaterialHistoryRecord.fingerprint == record.fingerprint,
                )
            )
            if exists is not None:
                continue
            db.add(record)
            await db.flush()
            await _index_record(record)
            created += 1
        if upload:
            upload.confirmed_by = confirmed_by
            upload.confirmed_at = datetime.now(timezone.utc)
        return created

    @staticmethod
    async def list_records(
        filters: MaterialHistoryFilter,
        team_id: int,
        db: AsyncSession,
    ) -> list[MaterialHistoryOut]:
        """按团队和筛选条件查询长期材料历史。"""
        stmt = (
            select(MaterialHistoryRecord, Project.id, Project.name)
            .options(
                selectinload(MaterialHistoryRecord.uploaded_user),
                selectinload(MaterialHistoryRecord.confirmed_user),
            )
            .outerjoin(Project, MaterialHistoryRecord.project_id == Project.id)
            .where(MaterialHistoryRecord.team_id == team_id)
            .order_by(MaterialHistoryRecord.quote_date.desc(), MaterialHistoryRecord.id.desc())
        )
        if filters.supplier_name:
            stmt = stmt.where(MaterialHistoryRecord.supplier_name.contains(filters.supplier_name.strip()))
        if filters.material_name:
            stmt = stmt.where(MaterialHistoryRecord.material_name.contains(filters.material_name.strip()))
        if filters.project_id:
            stmt = stmt.where(MaterialHistoryRecord.project_id == filters.project_id)
        if filters.date_from:
            stmt = stmt.where(MaterialHistoryRecord.quote_date >= filters.date_from)
        if filters.date_to:
            stmt = stmt.where(MaterialHistoryRecord.quote_date <= filters.date_to)
        rows = (await db.execute(stmt)).all()
        return [_to_out(record, project_id, project_name) for record, project_id, project_name in rows]

    @staticmethod
    async def update_from_receipt(
        receipt: Receipt, team_id: int, db: AsyncSession
    ) -> int:
        """收货确认后更新对应供应商材料的履约信息。"""
        supplier_order = await db.get(SupplierOrder, receipt.supplier_order_id)
        if supplier_order is None:
            return 0
        updated = 0
        for item in receipt.items:
            stmt = (
                select(MaterialHistoryRecord)
                .where(
                    MaterialHistoryRecord.team_id == team_id,
                    MaterialHistoryRecord.supplier_name == (item.supplier_name or ""),
                    MaterialHistoryRecord.material_name == item.species,
                    MaterialHistoryRecord.spec == item.spec,
                )
                .order_by(MaterialHistoryRecord.id.desc())
            )
            record = (await db.execute(stmt)).scalars().first()
            if record is None:
                continue
            record.final_price = item.final_price or record.final_price
            record.ordered_at = supplier_order.ordered_at
            record.arrived_at = item.arrived_at
            record.receipt_status = "received"
            updated += 1
        return updated


def _build_record(
    quote: Quote,
    item,
    team_id: int,
    quote_date: date,
    source_file: str,
    uploaded_by: int,
    confirmed_by: int,
    project_id: int | None = None,
) -> MaterialHistoryRecord:
    """从报价项构造长期历史记录。"""
    supplier = (quote.supplier_name or "").strip()
    material = item.species.strip()
    spec = (item.spec or "").strip()
    unit = (item.unit or "").strip() if hasattr(item, "unit") else ""
    fingerprint = _fingerprint(
        team_id, supplier, material, spec, item.quantity, unit,
        item.unit_price, item.total_price, item.final_price, quote_date, item.valid_until,
        item.delivery_days, item.payment_terms,
    )
    return MaterialHistoryRecord(
        team_id=team_id,
        project_id=project_id,
        supplier_name=supplier,
        material_name=material,
        spec=spec,
        quantity=item.quantity,
        unit=unit,
        quote_price=item.unit_price,
        total_price=item.total_price,
        final_price=item.final_price,
        quote_date=quote_date,
        valid_until=item.valid_until,
        delivery_days=item.delivery_days,
        payment_terms=item.payment_terms,
        source_file=source_file,
        source_quote_id=quote.id,
        uploaded_by=uploaded_by,
        confirmed_by=confirmed_by,
        fingerprint=fingerprint,
    )


def _fingerprint(*values: object) -> str:
    """按完整业务字段生成团队内去重指纹。"""
    normalized = [value.isoformat() if isinstance(value, (date, datetime)) else value for value in values]
    raw = json.dumps(normalized, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _resolve_project_id(order_id: int, db: AsyncSession) -> int | None:
    """通过报价所属采购单解析项目 ID，采购单不存在时返回 None。"""
    return await db.scalar(select(PurchaseOrder.project_id).where(PurchaseOrder.id == order_id))


async def _index_record(record: MaterialHistoryRecord) -> None:
    """将记录写入向量库；SQLite 记录作为精确查询的主数据。"""
    try:
        from app.services.knowledge_base import KnowledgeBaseManager

        await KnowledgeBaseManager.index_material_record(record)
    except Exception as exc:
        logger.warning("长期材料记录向量索引失败，保留结构化记录：%s", exc)


def _to_out(record: MaterialHistoryRecord, project_id: int | None = None, project_name: str | None = None) -> MaterialHistoryOut:
    """将 ORM 记录转换为接口输出。"""
    uploaded = record.uploaded_user
    confirmed = record.confirmed_user
    return MaterialHistoryOut(
        record_id=record.id,
        supplier_name=record.supplier_name,
        material_name=record.material_name,
        spec=record.spec,
        quantity=float(record.quantity) if record.quantity is not None else None,
        unit=record.unit,
        quote_price=float(record.quote_price) if record.quote_price is not None else None,
        total_price=float(record.total_price) if record.total_price is not None else None,
        final_price=float(record.final_price) if record.final_price is not None else None,
        quote_date=record.quote_date,
        valid_until=record.valid_until,
        delivery_days=record.delivery_days,
        payment_terms=record.payment_terms,
        project_id=project_id if project_id is not None else record.project_id,
        project_name=project_name,
        source_file=record.source_file,
        uploaded_by=record.uploaded_by,
        uploaded_by_name=_user_name(uploaded),
        confirmed_by=record.confirmed_by,
        confirmed_by_name=_user_name(confirmed),
        created_at=record.created_at,
        ordered_at=record.ordered_at,
        arrived_at=record.arrived_at,
        receipt_status=record.receipt_status,
    )


def _user_name(user) -> str | None:
    """优先返回显示名，没有显示名时返回用户名。"""
    if user is None:
        return None
    return user.display_name or user.username
