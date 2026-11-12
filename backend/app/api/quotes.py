"""报价单上传、确认、查询接口。"""
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_team_id
from app.core.response import APIResponse
from app.core.config import settings
from app.schemas.auth import UserInfo
from app.schemas.quote import QuoteCreateInput
from app.services.quote_service import QuoteService

router = APIRouter()


@router.post("/parse", summary="上传并解析供应商报价单")
async def parse_quote_file(
    order_id: int | None = Form(None),
    file: UploadFile = File(...),
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """上传报价文件，返回等待用户确认的报价结构。"""
    from app.agents.quote import parse_quote
    from app.storage.local_storage import local_storage

    stored = await local_storage.save(file, team_id, "quote")
    items = parse_quote(f"{settings.UPLOAD_DIR}/{stored.path}")
    upload = await QuoteService.register_upload(
        team_id, current_user.user_id, stored.path, stored.original_name, db
    )
    await db.commit()
    return APIResponse.ok({
        "order_id": order_id,
        "upload_id": upload.id,
        "file_path": stored.path,
        "original_name": stored.original_name,
        "items": [item.model_dump(mode="json") for item in items],
    })


@router.post("", summary="确认保存供应商报价")
async def create_quote(
    data: QuoteCreateInput,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """保存用户修改并确认后的报价单。"""
    out = await QuoteService.create(data, team_id, db, current_user.user_id)
    await db.commit()
    return APIResponse.ok(out.model_dump())


@router.get("", summary="查询采购单报价")
async def list_quotes(
    order_id: int | None = None,
    project_id: int | None = None,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """按项目或采购单返回当前团队已确认的供应商报价。"""
    if order_id is not None:
        out = await QuoteService.list_by_order(order_id, team_id, db)
    else:
        out = await QuoteService.list_all(team_id, db, project_id=project_id)
    return APIResponse.ok([item.model_dump() for item in out])


@router.delete("/{quote_id}", summary="删除报价记录")
async def delete_quote(
    quote_id: int,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """删除当前团队报价管理记录，保留长期材料历史。"""
    if current_user.role != "owner":
        from app.core.exceptions import PermissionDeniedError
        raise PermissionDeniedError("只有团队管理员可以删除报价")
    await QuoteService.delete(quote_id, team_id, db)
    await db.commit()
    return APIResponse.ok()
