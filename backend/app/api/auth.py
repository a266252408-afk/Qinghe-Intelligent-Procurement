"""认证路由：登录/注册、团队管理"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.response import APIResponse
from app.schemas.auth import (
    LoginRequest, RegisterRequest, TeamCreate, TeamInvitationCreate, TeamJoin, UserInfo,
)
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/login", summary="登录")
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)) -> APIResponse:
    token = await AuthService.login(data, db)
    await db.commit()
    return APIResponse.ok(token.model_dump())


@router.post("/register", summary="注册")
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)) -> APIResponse:
    """按账号类型注册；管理员同时创建团队，采购员等待邀请。"""
    token = await AuthService.register(data, db)
    await db.commit()
    return APIResponse.ok(token.model_dump())


@router.get("/me", summary="获取当前用户信息")
async def me(current_user: UserInfo = Depends(get_current_user)) -> APIResponse:
    return APIResponse.ok(current_user.model_dump())


@router.post("/team", summary="创建团队")
async def create_team(
    data: TeamCreate,
    current_user: UserInfo = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    result = await AuthService.create_team(current_user.user_id, data, db)
    await db.commit()
    return APIResponse.ok(result.model_dump())


@router.post("/team/join", summary="加入团队（邀请码）")
async def join_team(
    data: TeamJoin,
    current_user: UserInfo = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    info = await AuthService.join_team(current_user.user_id, data, db)
    await db.commit()
    return APIResponse.ok(info.model_dump())


@router.post("/team/leave", summary="退出当前团队")
async def leave_team(
    current_user: UserInfo = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """退出当前团队；管理员需有成员接管权限后才能退出。"""
    token = await AuthService.leave_team(current_user.user_id, db)
    await db.commit()
    return APIResponse.ok(token.model_dump())


@router.get("/team/invitations", summary="查看团队邀请")
async def list_invitations(
    current_user: UserInfo = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    invitations = await AuthService.list_invitations(current_user.user_id, db)
    return APIResponse.ok([item.model_dump() for item in invitations])


@router.post("/team/invitations", summary="管理员邀请采购员")
async def send_invitation(
    data: TeamInvitationCreate,
    current_user: UserInfo = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    invitation = await AuthService.send_invitation(current_user.user_id, data, db)
    await db.commit()
    return APIResponse.ok(invitation.model_dump())


@router.post("/team/invitations/{invitation_id}/accept", summary="接受团队邀请")
async def accept_invitation(
    invitation_id: int,
    current_user: UserInfo = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    token = await AuthService.respond_invitation(current_user.user_id, invitation_id, True, db)
    await db.commit()
    return APIResponse.ok(token.model_dump() if token else None)


@router.post("/team/invitations/{invitation_id}/reject", summary="拒绝团队邀请")
async def reject_invitation(
    invitation_id: int,
    current_user: UserInfo = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    await AuthService.respond_invitation(current_user.user_id, invitation_id, False, db)
    await db.commit()
    return APIResponse.ok()
