# SDD — 认证权限服务（auth_service）

> **依据**：system-design.md §2.2.10，tech-stack.md §8，PRD §3.2，PRD §FR-10
> **代码位置**：`backend/app/services/auth_service.py`

---

## 1. 功能描述

实现明确的登录/注册逻辑：登录只校验已有账号；注册按账号类型区分管理员和采购员。管理员注册时创建团队，采购员注册后保持无团队状态，等待管理员邀请并明确同意。
生成 / 校验 JWT Token（载荷含 `user_id / team_id / role / exp`）。
支持团队创建（创建者即主管 owner）、管理员按用户名邀请采购员、采购员接受/拒绝邀请；保留邀请码加入接口用于兼容旧客户端。
支持成员退出团队；管理员退出时必须有成员接管权限。
密码使用 bcrypt 哈希存储，不存明文。

---

## 2. 接口签名

```python
from app.schemas.auth import (
    LoginRequest, Token, UserInfo,
    TeamCreate, TeamCreateResult, TeamJoin
)

class AuthService:

    @staticmethod
    async def login_or_register(
        data: LoginRequest,       # 包含 username / password
        db: AsyncSession,         # 数据库会话
    ) -> Token:
        """首次调用自动注册并返回 Token；已有账号校验密码后返回 Token。"""

    @staticmethod
    async def verify_token(
        token: str,               # Bearer Token 原始字符串
    ) -> UserInfo:
        """校验 JWT 签名与有效期，返回用户信息；无效或过期则抛出异常。"""

    @staticmethod
    async def create_team(
        creator_id: int,          # 创建者用户 ID
        data: TeamCreate,         # 包含 name
        db: AsyncSession,
    ) -> TeamCreateResult:
        """创建团队，创建者自动成为 owner；生成并返回邀请码。"""

    @staticmethod
    async def join_team(
        user_id: int,             # 加入者用户 ID
        data: TeamJoin,           # 包含 invite_code
        db: AsyncSession,
    ) -> UserInfo:
        """校验邀请码，将用户加入团队（角色 member）；返回更新后的 UserInfo。"""

    @staticmethod
    async def get_current_user(
        user_id: int,             # 从 JWT 解析出的用户 ID
        db: AsyncSession,
    ) -> UserInfo:
        """查询当前用户信息（含 team_id / role）。"""
```

### Pydantic 模型（`backend/app/schemas/auth.py`）

```python
class LoginRequest(BaseModel):
    username: str    # 用户名
    password: str    # 明文密码（传输层走 HTTPS）

class RegisterRequest(LoginRequest):
    account_type: str = "admin"      # admin / purchaser；旧客户端未传时兼容管理员流程
    team_name: str | None = None      # 管理员注册时创建的团队名称

class Token(BaseModel):
    access_token: str   # JWT 字符串
    token_type: str = "bearer"

class UserInfo(BaseModel):
    user_id: int
    username: str
    display_name: str
    team_id: int | None    # 未加入团队时为 None
    team_name: str | None  # 当前团队名称
    role: str | None       # "owner" / "member" / None

class TeamCreate(BaseModel):
    name: str              # 团队名称

class TeamCreateResult(BaseModel):
    team_id: int
    name: str
    invite_code: str       # 6 位随机字母数字邀请码

class TeamJoin(BaseModel):
    invite_code: str       # 邀请码

class TeamInvitationCreate(BaseModel):
    username: str           # 已注册采购员用户名

class TeamInvitationOut(BaseModel):
    invitation_id: int
    team_id: int
    team_name: str
    inviter_username: str
    invitee_username: str
    status: str              # pending / accepted / rejected
```

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `python-jose[cryptography]` | JWT 生成与校验 |
| `bcrypt` | 密码哈希与校验 |
| `app.core.config.settings` | `JWT_SECRET / JWT_ALGORITHM / JWT_EXPIRE_MINUTES` |
| `app.models.user.User` | ORM：用户表 |
| `app.models.team.Team` | ORM：团队表 |
| `app.models.team_member.TeamMember` | ORM：团队成员关联表 |
| `app.core.exceptions` | 抛出业务异常 |

---

## 4. 异常处理

| 异常类 | 触发条件 | HTTP 状态码 |
|:------- |:-------- |:----------- |
| `InvalidCredentialsError` | 密码不匹配 | 401 |
| `TokenExpiredError` | JWT exp 已过期 | 401 |
| `InvalidTokenError` | JWT 签名无效或格式错误 | 401 |
| `InvalidInviteCodeError` | 邀请码不存在或已失效 | 400 |
| `AlreadyInTeamError` | 用户已属于某个团队（MVP 一对一限制） | 409 |
| `TeamNameRequiredError` | 显式管理员注册未填写团队名称 | 422 |
| `UserNotFoundError` | 管理员邀请的用户名不存在 | 404 |
| `InvitationAlreadyExistsError` | 已存在待处理邀请 | 409 |
| `InvitationNotFoundError` | 邀请不存在或已处理 | 404 |
| `CannotLeaveTeamError` | 管理员退出时没有可接管成员 | 409 |

MVP 约束：一个用户只能属于一个团队；退出当前团队后才允许加入其他团队。
