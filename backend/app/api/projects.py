"""项目管理路由"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_team_id
from app.core.exceptions import PermissionDeniedError
from app.core.response import APIResponse
from app.schemas.auth import UserInfo
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.project_service import ProjectService

router = APIRouter()


@router.post("", summary="创建项目")
async def create_project(
    data: ProjectCreate,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    out = await ProjectService.create_project(data, current_user.user_id, team_id, db)
    await db.commit()
    return APIResponse.ok(out.model_dump())


@router.get("", summary="项目列表")
async def list_projects(
    status: str | None = None,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    out = await ProjectService.list_projects(team_id, status, db)
    return APIResponse.ok(out.model_dump())


@router.get("/{project_id}", summary="项目详情")
async def get_project(
    project_id: int,
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    out = await ProjectService.get_project(project_id, team_id, db)
    return APIResponse.ok(out.model_dump())


@router.patch("/{project_id}", summary="更新项目")
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    if current_user.role != "owner":
        raise PermissionDeniedError("只有团队管理员可以修改项目")
    out = await ProjectService.update_project(project_id, data, team_id, db)
    await db.commit()
    return APIResponse.ok(out.model_dump())


@router.delete("/{project_id}", summary="删除项目（软删除）")
async def delete_project(
    project_id: int,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    if current_user.role != "owner":
        raise PermissionDeniedError("只有团队管理员可以删除项目")
    await ProjectService.delete_project(project_id, team_id, db)
    await db.commit()
    return APIResponse.ok()
