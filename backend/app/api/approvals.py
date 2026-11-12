"""审批路由"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_team_id
from app.core.response import APIResponse
from app.schemas.auth import UserInfo
from app.services.approval_service import ApprovalService

router = APIRouter()


class RejectBody(BaseModel):
    reason: str


@router.get("", summary="待审批采购单列表")
async def list_pending(
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    out = await ApprovalService.list_pending(team_id, db, current_user.role)
    return APIResponse.ok(out.model_dump())


@router.post("/{order_id}/approve", summary="审批通过")
async def approve(
    order_id: int,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    record = await ApprovalService.approve(order_id, current_user.user_id, team_id, db, current_user.role)
    await db.commit()
    return APIResponse.ok(record.model_dump())


@router.post("/{order_id}/reject", summary="审批驳回")
async def reject(
    order_id: int,
    body: RejectBody,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    record = await ApprovalService.reject(order_id, current_user.user_id, body.reason, team_id, db, current_user.role)
    await db.commit()
    return APIResponse.ok(record.model_dump())


@router.get("/{order_id}/history", summary="采购单审批历史")
async def approval_history(
    order_id: int,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    records = await ApprovalService.get_approval_history(order_id, team_id, db)
    return APIResponse.ok([r.model_dump() for r in records])
