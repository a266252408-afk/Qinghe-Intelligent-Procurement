"""认证服务测试"""
import pytest

from app.services.auth_service import AuthService
from app.schemas.auth import LoginRequest, TeamCreate, TeamJoin
from app.core.exceptions import (
    AlreadyInTeamError,
    CannotLeaveTeamError,
    InvalidCredentialsError,
    InvalidInviteCodeError,
)


pytestmark = pytest.mark.asyncio


async def test_login_or_register_creates_user(db):
    """首次登录自动注册，返回 Token"""
    req = LoginRequest(username="alice", password="secret")
    token = await AuthService.login_or_register(req, db)
    assert token.access_token


async def test_login_or_register_same_user_twice(db):
    """相同用户名第二次登录使用正确密码成功"""
    req = LoginRequest(username="bob", password="pass123")
    await AuthService.login_or_register(req, db)
    token = await AuthService.login_or_register(req, db)
    assert token.access_token


async def test_login_wrong_password_raises(db):
    """密码错误应抛出 InvalidCredentialsError"""
    req = LoginRequest(username="carol", password="right")
    await AuthService.login_or_register(req, db)
    with pytest.raises(InvalidCredentialsError):
        await AuthService.login_or_register(LoginRequest(username="carol", password="wrong"), db)


async def test_create_team_and_get_invite_code(db):
    """创建团队应返回邀请码，长度 6"""
    req = LoginRequest(username="owner1", password="pass")
    token = await AuthService.login_or_register(req, db)

    from app.core.security import decode_token
    payload = decode_token(token.access_token)
    user_id = payload["user_id"]

    result = await AuthService.create_team(user_id, TeamCreate(name="测试团队"), db)
    assert len(result.invite_code) == 6
    assert result.name == "测试团队"


async def test_join_team_with_valid_invite_code(db):
    """通过有效邀请码加入团队"""
    # 创建 owner
    t1 = await AuthService.login_or_register(LoginRequest(username="owner2", password="p"), db)
    from app.core.security import decode_token
    owner_id = decode_token(t1.access_token)["user_id"]
    team_result = await AuthService.create_team(owner_id, TeamCreate(name="T2"), db)

    # 新用户加入
    t2 = await AuthService.login_or_register(LoginRequest(username="member1", password="p"), db)
    member_id = decode_token(t2.access_token)["user_id"]
    token = await AuthService.join_team(member_id, TeamJoin(invite_code=team_result.invite_code), db)
    payload = decode_token(token.access_token)
    assert payload["team_id"] == team_result.team_id
    assert payload["role"] == "member"


async def test_join_team_invalid_code_raises(db):
    """邀请码无效应抛出异常"""
    t = await AuthService.login_or_register(LoginRequest(username="nobody", password="p"), db)
    from app.core.security import decode_token
    uid = decode_token(t.access_token)["user_id"]
    with pytest.raises(InvalidInviteCodeError):
        await AuthService.join_team(uid, TeamJoin(invite_code="BADCOD"), db)


async def test_already_in_team_raises(db):
    """已在团队中再次创建团队应抛出异常"""
    t = await AuthService.login_or_register(LoginRequest(username="dupuser", password="p"), db)
    from app.core.security import decode_token
    uid = decode_token(t.access_token)["user_id"]
    await AuthService.create_team(uid, TeamCreate(name="First"), db)
    with pytest.raises(AlreadyInTeamError):
        await AuthService.create_team(uid, TeamCreate(name="Second"), db)


async def test_member_can_leave_and_join_another_team(db):
    """成员退出原团队后才能加入新团队。"""
    from app.core.security import decode_token

    owner_token = await AuthService.login_or_register(LoginRequest(username="leave_owner", password="p"), db)
    owner_id = decode_token(owner_token.access_token)["user_id"]
    first_team = await AuthService.create_team(owner_id, TeamCreate(name="First"), db)

    member_token = await AuthService.login_or_register(LoginRequest(username="leave_member", password="p"), db)
    member_id = decode_token(member_token.access_token)["user_id"]
    await AuthService.join_team(member_id, TeamJoin(invite_code=first_team.invite_code), db)

    left_token = await AuthService.leave_team(member_id, db)
    assert decode_token(left_token.access_token)["team_id"] is None

    second_owner = await AuthService.login_or_register(LoginRequest(username="second_owner", password="p"), db)
    second_owner_id = decode_token(second_owner.access_token)["user_id"]
    second_team = await AuthService.create_team(second_owner_id, TeamCreate(name="Second"), db)
    joined = await AuthService.join_team(member_id, TeamJoin(invite_code=second_team.invite_code), db)
    assert decode_token(joined.access_token)["team_id"] == second_team.team_id


async def test_owner_leaves_and_transfers_role(db):
    """管理员退出时将管理员角色交给团队成员。"""
    from app.core.security import decode_token

    owner_token = await AuthService.login_or_register(LoginRequest(username="transfer_owner", password="p"), db)
    owner_id = decode_token(owner_token.access_token)["user_id"]
    team = await AuthService.create_team(owner_id, TeamCreate(name="Transfer"), db)
    member_token = await AuthService.login_or_register(LoginRequest(username="transfer_member", password="p"), db)
    member_id = decode_token(member_token.access_token)["user_id"]
    await AuthService.join_team(member_id, TeamJoin(invite_code=team.invite_code), db)

    left = await AuthService.leave_team(owner_id, db)
    assert decode_token(left.access_token)["team_id"] is None
    current_member = await AuthService.get_current_user(member_id, db)
    assert current_member.role == "owner"


async def test_owner_without_replacement_cannot_leave(db):
    """没有接管成员时管理员不能退出，避免团队失去管理员。"""
    from app.core.security import decode_token

    token = await AuthService.login_or_register(LoginRequest(username="sole_owner", password="p"), db)
    owner_id = decode_token(token.access_token)["user_id"]
    await AuthService.create_team(owner_id, TeamCreate(name="Sole"), db)
    with pytest.raises(CannotLeaveTeamError):
        await AuthService.leave_team(owner_id, db)
