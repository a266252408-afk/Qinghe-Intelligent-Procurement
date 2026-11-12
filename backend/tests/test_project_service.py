"""项目服务测试"""
import pytest

from app.services.auth_service import AuthService
from app.services.project_service import ProjectService
from app.schemas.auth import LoginRequest, TeamCreate
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.core.exceptions import ProjectNotFoundError, DuplicateProjectNameError
from app.core.security import decode_token


pytestmark = pytest.mark.asyncio


async def _setup_user_team(db):
    """创建用户并建立团队，返回 (user_id, team_id)"""
    token = await AuthService.login_or_register(LoginRequest(username="pm_user", password="p"), db)
    uid = decode_token(token.access_token)["user_id"]
    team = await AuthService.create_team(uid, TeamCreate(name="PM Team"), db)
    return uid, team.team_id


async def test_create_and_get_project(db):
    uid, team_id = await _setup_user_team(db)
    data = ProjectCreate(name="绿化工程A", budget=100000.0)
    out = await ProjectService.create_project(data, uid, team_id, db)
    assert out.name == "绿化工程A"
    assert out.status == "active"

    fetched = await ProjectService.get_project(out.project_id, team_id, db)
    assert fetched.project_id == out.project_id


async def test_list_projects_returns_own_projects(db):
    uid, team_id = await _setup_user_team(db)
    await ProjectService.create_project(ProjectCreate(name="P1"), uid, team_id, db)
    await ProjectService.create_project(ProjectCreate(name="P2"), uid, team_id, db)
    result = await ProjectService.list_projects(team_id, None, db)
    assert result.total == 2


async def test_update_project(db):
    uid, team_id = await _setup_user_team(db)
    p = await ProjectService.create_project(ProjectCreate(name="Old Name"), uid, team_id, db)
    updated = await ProjectService.update_project(
        p.project_id, ProjectUpdate(name="New Name"), team_id, db
    )
    assert updated.name == "New Name"


async def test_soft_delete_project(db):
    uid, team_id = await _setup_user_team(db)
    p = await ProjectService.create_project(ProjectCreate(name="ToDelete"), uid, team_id, db)
    await ProjectService.delete_project(p.project_id, team_id, db)

    with pytest.raises(ProjectNotFoundError):
        await ProjectService.get_project(p.project_id, team_id, db)


async def test_cross_team_access_denied(db):
    """其他团队无法访问该项目"""
    uid, team_id = await _setup_user_team(db)
    p = await ProjectService.create_project(ProjectCreate(name="Secret"), uid, team_id, db)

    with pytest.raises(ProjectNotFoundError):
        await ProjectService.get_project(p.project_id, team_id + 999, db)


async def test_duplicate_project_name_rejected(db):
    uid, team_id = await _setup_user_team(db)
    await ProjectService.create_project(ProjectCreate(name="同名项目"), uid, team_id, db)
    with pytest.raises(DuplicateProjectNameError):
        await ProjectService.create_project(ProjectCreate(name="同名项目"), uid, team_id, db)
