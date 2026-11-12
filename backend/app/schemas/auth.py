"""认证相关 Pydantic Schema"""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(LoginRequest):
    """注册类型：管理员创建团队，采购员等待团队邀请。"""
    account_type: Literal["admin", "purchaser"] = "admin"
    team_name: str | None = Field(default=None, max_length=100)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserInfo(BaseModel):
    user_id: int
    username: str
    display_name: str = ""
    team_id: int | None = None
    team_name: str | None = None
    role: str | None = None        # "owner" / "member" / None


class TeamCreate(BaseModel):
    name: str


class TeamCreateResult(BaseModel):
    team_id: int
    name: str
    invite_code: str               # 6 位大写字母+数字


class TeamCreateToken(BaseModel):
    """创建团队后返回，包含邀请码和含 team_id 的新 Token"""
    team_id: int
    name: str
    invite_code: str
    access_token: str
    token_type: str = "bearer"


class TeamJoin(BaseModel):
    invite_code: str


class TeamInvitationCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)


class TeamInvitationOut(BaseModel):
    invitation_id: int
    team_id: int
    team_name: str
    inviter_username: str
    invitee_username: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
