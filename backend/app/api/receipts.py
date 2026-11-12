"""收货管理接口。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_team_id
from app.core.response import APIResponse
from app.core.exceptions import PermissionDeniedError
from app.schemas.auth import UserInfo
from app.schemas.receipt import ReceiptUpdate
from app.services.receipt_service import ReceiptService

router = APIRouter()


@router.get("", summary="收货单列表")
async def list_receipts(
    team_id: int = Depends(get_team_id), db: AsyncSession = Depends(get_db)
) -> APIResponse:
    out = await ReceiptService.list_receipts(team_id, db)
    return APIResponse.ok([item.model_dump() for item in out])


@router.get("/{receipt_id}", summary="收货单详情")
async def get_receipt(
    receipt_id: int,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    out = await ReceiptService.get_receipt(receipt_id, team_id, db)
    return APIResponse.ok(out.model_dump())


@router.delete("/{receipt_id}", summary="删除收货单")
async def delete_receipt(
    receipt_id: int,
    current_user: UserInfo = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """仅团队管理员可以删除收货单。"""
    if current_user.role != "owner":
        raise PermissionDeniedError("只有团队管理员可以删除收货单")
    await ReceiptService.delete(receipt_id, current_user.team_id, db)
    await db.commit()
    return APIResponse.ok()


@router.patch("/{receipt_id}", summary="保存收货明细")
async def update_receipt(
    receipt_id: int,
    data: ReceiptUpdate,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    out = await ReceiptService.update_receipt(receipt_id, data, team_id, db)
    await db.commit()
    return APIResponse.ok(out.model_dump())


@router.post("/{receipt_id}/confirm", summary="一键确认收货")
async def confirm_receipt(
    receipt_id: int,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    out = await ReceiptService.confirm_all(receipt_id, team_id, db)
    await db.commit()
    return APIResponse.ok(out.model_dump())
