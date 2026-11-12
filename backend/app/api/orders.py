"""采购单路由：CRUD + 状态机操作 + 询价单生成 + 比价"""
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_team_id
from app.core.response import APIResponse
from app.core.exceptions import PermissionDeniedError
from app.core.config import settings
from app.schemas.auth import UserInfo
from app.schemas.compare import CompareInput
from app.schemas.inquiry import InquiryGenerateInput
from app.schemas.order import OrderCreate, OrderItemCreate, OrderUpdate
from app.services.order_service import PurchaseOrderService
from app.services.supplier_order_service import SupplierOrderService

router = APIRouter()


@router.get("/inquiry/templates", summary="询价模板列表")
async def list_inquiry_templates(_: int = Depends(get_team_id)) -> APIResponse:
    """返回当前团队可用的询价模板"""
    from app.agents.inquiry import InquiryAgent
    return APIResponse.ok([t.model_dump() for t in InquiryAgent().list_templates()])


# ── 采购单 CRUD ───────────────────────────────────────────────────────────

@router.post("", summary="创建采购单")
async def create_order(
    data: OrderCreate,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    out = await PurchaseOrderService.create_order(data, current_user.user_id, team_id, db)
    await db.commit()
    return APIResponse.ok(out.model_dump())


@router.get("", summary="采购单列表")
async def list_orders(
    project_id: int | None = None,
    status: str | None = None,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    out = await PurchaseOrderService.list_orders(team_id, project_id, status, None, db)
    return APIResponse.ok(out.model_dump())


@router.delete("/{order_id}", summary="删除采购单")
async def delete_order(
    order_id: int,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """删除当前团队采购单及其关联管理记录。"""
    if current_user.role != "owner":
        raise PermissionDeniedError("只有团队管理员可以删除采购单")
    await PurchaseOrderService.delete_order(order_id, team_id, db)
    await db.commit()
    return APIResponse.ok()


@router.get("/supplier-orders", summary="下单管理列表")
async def list_supplier_orders(
    project_id: int | None = None,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    out = await PurchaseOrderService.list_supplier_orders(team_id, db, project_id)
    return APIResponse.ok([item.model_dump() for item in out])


@router.get("/supplier-orders/{supplier_order_id}", summary="下单详情")
async def get_supplier_order(
    supplier_order_id: int,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    out = await PurchaseOrderService.get_supplier_order(supplier_order_id, team_id, db)
    return APIResponse.ok(out.model_dump())


@router.delete("/supplier-orders/{supplier_order_id}", summary="删除下单记录")
async def delete_supplier_order(
    supplier_order_id: int,
    current_user: UserInfo = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """仅团队管理员可以删除下单记录。"""
    if current_user.role != "owner":
        raise PermissionDeniedError("只有团队管理员可以删除下单记录")
    await SupplierOrderService.delete(supplier_order_id, current_user.team_id, db)
    await db.commit()
    return APIResponse.ok()


@router.get("/supplier-orders/{supplier_order_id}/download", summary="下载下单表")
async def download_supplier_order(
    supplier_order_id: int,
    file_format: str = "xlsx",
    item_id: int | None = None,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    """下载整张下单表或指定下单项。"""
    return await SupplierOrderService.export(
        supplier_order_id, team_id, file_format, db, item_id
    )


@router.get("/{order_id}", summary="采购单详情")
async def get_order(
    order_id: int,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    out = await PurchaseOrderService.get_order(order_id, team_id, db)
    return APIResponse.ok(out.model_dump())


@router.put("/{order_id}", summary="更新采购单名称和备注")
async def update_order(
    order_id: int,
    data: OrderUpdate,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """更新草稿采购单的自定义名称和备注。"""
    out = await PurchaseOrderService.update_order(order_id, data, team_id, db)
    await db.commit()
    return APIResponse.ok(out.model_dump())


@router.patch("/{order_id}", summary="兼容更新采购单名称和备注")
async def patch_order(
    order_id: int,
    data: OrderUpdate,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """兼容旧前端或代理对 PATCH 方法的调用。"""
    out = await PurchaseOrderService.update_order(order_id, data, team_id, db)
    await db.commit()
    return APIResponse.ok(out.model_dump())


@router.get("/{order_id}/supplier-options", summary="采购项供应商报价选项")
async def supplier_options(
    order_id: int,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """返回采购单材料对应的当前团队供应商报价。"""
    out = await PurchaseOrderService.list_supplier_options(order_id, team_id, db)
    return APIResponse.ok([item.model_dump() for item in out])


# ── 采购项 ────────────────────────────────────────────────────────────────

@router.put("/{order_id}/items", summary="覆盖保存采购项")
async def save_items(
    order_id: int,
    items: list[OrderItemCreate],
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    out = await PurchaseOrderService.save_items(order_id, items, team_id, db)
    await db.commit()
    return APIResponse.ok([i.model_dump() for i in out])


# ── 状态操作 ──────────────────────────────────────────────────────────────

@router.post("/{order_id}/submit", summary="提交审批")
async def submit_for_approval(
    order_id: int,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    out = await PurchaseOrderService.submit_for_approval(order_id, team_id, db)
    await db.commit()
    return APIResponse.ok(out.model_dump())


@router.post("/{order_id}/receive", summary="确认收货")
async def confirm_receipt(
    order_id: int,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    out = await PurchaseOrderService.confirm_receipt(order_id, team_id, db)
    await db.commit()
    return APIResponse.ok(out.model_dump())


# ── 询价单生成 ────────────────────────────────────────────────────────────

@router.post("/{order_id}/inquiry", summary="生成询价单 Excel")
async def generate_inquiry(
    order_id: int,
    data: InquiryGenerateInput,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    from app.agents.inquiry import InquiryAgent
    data.order_id = order_id
    out = await InquiryAgent().generate(data, team_id, str(current_user.user_id), db)
    await db.commit()
    return APIResponse.ok(out.model_dump())


@router.get("/{order_id}/inquiry/download", summary="下载询价单 Excel")
async def download_inquiry(
    order_id: int,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """校验采购单团队归属后下载最近生成的询价单"""
    from sqlalchemy import select
    from app.models.quote import InquirySheet
    from app.models.order import PurchaseOrder
    from app.models.project import Project

    stmt = (
        select(InquirySheet)
        .join(PurchaseOrder, InquirySheet.order_id == PurchaseOrder.id)
        .join(Project, PurchaseOrder.project_id == Project.id)
        .where(InquirySheet.order_id == order_id, Project.team_id == team_id)
        .order_by(InquirySheet.created_at.desc())
    )
    sheet = (await db.execute(stmt)).scalars().first()
    if sheet is None:
        from app.core.exceptions import FileNotFoundAppError
        raise FileNotFoundAppError()
    path = Path(settings.UPLOAD_DIR) / sheet.file_path
    if not path.is_file():
        from app.core.exceptions import FileNotFoundAppError
        raise FileNotFoundAppError()
    return FileResponse(path, filename=path.name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ── 比价 ──────────────────────────────────────────────────────────────────

@router.post("/{order_id}/compare", summary="执行比价分析")
async def compare(
    order_id: int,
    data: CompareInput,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    from app.agents.compare import CompareAgent
    data.order_id = order_id
    out = await CompareAgent().compare(data, team_id, str(current_user.user_id), db)
    return APIResponse.ok(out.model_dump())
