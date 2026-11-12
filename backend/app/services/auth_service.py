"""认证与权限服务
依据：docs/module-sdd/auth_service.md
"""
import asyncio
import random
import string

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AlreadyInTeamError,
    CannotLeaveTeamError,
    InvitationAlreadyExistsError,
    InvitationNotFoundError,
    InvalidCredentialsError,
    InvalidInviteCodeError,
    PermissionDeniedError,
    TeamNameRequiredError,
    UserNotFoundError,
    UsernameAlreadyExistsError,
)
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import Team, TeamInvitation, TeamMember, User
from app.schemas.auth import (
    LoginRequest, RegisterRequest, TeamCreate, TeamInvitationCreate,
    TeamInvitationOut, TeamJoin, Token, TeamCreateToken, UserInfo,
)


def _gen_invite_code(length: int = 6) -> str:
    """生成 N 位大写字母+数字邀请码"""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


class AuthService:

    @staticmethod
    async def login_or_register(data: LoginRequest, db: AsyncSession) -> Token:
        """兼容旧调用：已有账号登录，新账号注册。新 API 使用明确的 login/register。"""
        stmt = select(User).where(User.username == data.username)
        user = (await db.execute(stmt)).scalar_one_or_none()

        if user is None:
            # 首次：自动注册（bcrypt 是 CPU 密集操作，放线程池避免阻塞事件循环）
            user = User(
                username=data.username,
                password_hash=await asyncio.to_thread(hash_password, data.password),
                display_name=data.username,
                account_type="admin",
            )
            db.add(user)
            await db.flush()
        else:
            if not await asyncio.to_thread(verify_password, data.password, user.password_hash):
                raise InvalidCredentialsError()

        # 查询团队信息
        member, team = await AuthService._team_membership(user.id, db)

        token = create_access_token({
            "user_id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "team_id": member.team_id if member else None,
            "role": member.role if member else None,
            "team_name": team.name if team else None,
        })
        return Token(access_token=token)

    @staticmethod
    async def login(data: LoginRequest, db: AsyncSession) -> Token:
        """校验已有账号并返回 Token，不存在时拒绝登录。"""
        user = (await db.execute(
            select(User).where(User.username == data.username)
        )).scalar_one_or_none()
        ok = (
            user is not None
            and await asyncio.to_thread(verify_password, data.password, user.password_hash)
        )
        if not ok:
            raise InvalidCredentialsError()
        return await AuthService._token_for_user(user, db)

    @staticmethod
    async def register(data: RegisterRequest, db: AsyncSession) -> Token | TeamCreateToken:
        """创建新账号；用户名已存在时拒绝重复注册。"""
        exists = (await db.execute(
            select(User).where(User.username == data.username)
        )).scalar_one_or_none()
        if exists is not None:
            raise UsernameAlreadyExistsError()
        user = User(
            username=data.username,
            # bcrypt CPU 密集，放线程池避免阻塞事件循环
            password_hash=await asyncio.to_thread(hash_password, data.password),
            display_name=data.username,
            account_type=data.account_type,
        )
        db.add(user)
        await db.flush()
        if data.account_type == "admin":
            if "account_type" in data.model_fields_set and (
                not data.team_name or not data.team_name.strip()
            ):
                raise TeamNameRequiredError()
            if data.team_name and data.team_name.strip():
                return await AuthService.create_team(
                    user.id, TeamCreate(name=data.team_name.strip()), db
                )
        return await AuthService._token_for_user(user, db)

    @staticmethod
    async def _token_for_user(user: User, db: AsyncSession) -> Token:
        """根据用户及其团队成员关系生成 Token。"""
        member, team = await AuthService._team_membership(user.id, db)
        return Token(access_token=create_access_token({
            "user_id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "team_id": member.team_id if member else None,
            "role": member.role if member else None,
            "team_name": team.name if team else None,
        }))

    @staticmethod
    async def get_current_user(user_id: int, db: AsyncSession) -> UserInfo:
        """查询当前用户信息（含 team_id / role）"""
        user = await db.get(User, user_id)
        if user is None:
            raise PermissionDeniedError("用户不存在")

        member, team = await AuthService._team_membership(user_id, db)

        return UserInfo(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            team_id=member.team_id if member else None,
            role=member.role if member else None,
            team_name=team.name if team else None,
        )

    @staticmethod
    async def _team_membership(
        user_id: int, db: AsyncSession
    ) -> tuple[TeamMember | None, Team | None]:
        """读取用户当前团队和角色，MVP 保证一个用户最多一个团队。"""
        row = (await db.execute(
            select(TeamMember, Team)
            .join(Team, Team.id == TeamMember.team_id)
            .where(TeamMember.user_id == user_id)
        )).one_or_none()
        return row if row else (None, None)

    @staticmethod
    async def create_team(creator_id: int, data: TeamCreate, db: AsyncSession) -> "TeamCreateToken":
        """创建团队，创建者自动成为 owner；生成邀请码；返回含 team_id 的新 Token"""
        # MVP：一个用户只能属于一个团队
        creator = await db.get(User, creator_id)
        if creator is None:
            raise PermissionDeniedError("用户不存在")
        if creator.account_type == "purchaser":
            raise PermissionDeniedError("采购员不能创建团队，请等待管理员邀请")
        existing = (await db.execute(
            select(TeamMember).where(TeamMember.user_id == creator_id)
        )).scalar_one_or_none()
        if existing:
            raise AlreadyInTeamError()

        invite_code = _gen_invite_code()
        team = Team(name=data.name, creator_id=creator_id, invite_code=invite_code)
        db.add(team)
        await db.flush()

        member = TeamMember(team_id=team.id, user_id=creator_id, role="owner")
        db.add(member)
        await db.flush()

        token = create_access_token({
            "user_id": creator_id,
            "username": creator.username,
            "display_name": creator.display_name,
            "team_id": team.id,
            "role": "owner",
            "team_name": team.name,
        })
        return TeamCreateToken(
            team_id=team.id,
            name=team.name,
            invite_code=invite_code,
            access_token=token,
        )

    @staticmethod
    async def join_team(user_id: int, data: TeamJoin, db: AsyncSession) -> Token:
        """校验邀请码，将用户加入团队（角色 member），返回含 team_id 的新 Token"""
        existing = (await db.execute(
            select(TeamMember).where(TeamMember.user_id == user_id)
        )).scalar_one_or_none()
        if existing:
            raise AlreadyInTeamError()

        team = (await db.execute(
            select(Team).where(Team.invite_code == data.invite_code.upper())
        )).scalar_one_or_none()
        if team is None:
            raise InvalidInviteCodeError()

        member = TeamMember(team_id=team.id, user_id=user_id, role="member")
        db.add(member)
        await db.flush()

        user = await db.get(User, user_id)
        token = create_access_token({
            "user_id": user_id,
            "username": user.username if user else "",
            "display_name": user.display_name if user else "",
            "team_id": team.id,
            "role": "member",
            "team_name": team.name,
        })
        return Token(access_token=token)

    @staticmethod
    async def leave_team(user_id: int, db: AsyncSession) -> Token:
        """退出当前团队；管理员退出时将权限交给最早加入的成员。"""
        memberships = (await db.execute(
            select(TeamMember).where(TeamMember.user_id == user_id).order_by(TeamMember.id)
        )).scalars().all()
        if not memberships:
            raise PermissionDeniedError("当前账号尚未加入团队")
        if len(memberships) > 1:
            raise PermissionDeniedError("账号存在多个团队关系，请先清理团队成员数据")

        membership = memberships[0]
        if membership.role == "owner":
            replacement = (await db.execute(
                select(TeamMember).where(
                    TeamMember.team_id == membership.team_id,
                    TeamMember.user_id != user_id,
                ).order_by(TeamMember.id)
            )).scalars().first()
            if replacement is None:
                raise CannotLeaveTeamError()
            replacement.role = "owner"
            team = await db.get(Team, membership.team_id)
            if team:
                team.creator_id = replacement.user_id

        await db.delete(membership)
        await db.flush()
        user = await db.get(User, user_id)
        return await AuthService._token_for_user(user, db)

    @staticmethod
    async def send_invitation(
        inviter_id: int, data: TeamInvitationCreate, db: AsyncSession
    ) -> TeamInvitationOut:
        """管理员按用户名发出待确认邀请。"""
        member, team = await AuthService._team_membership(inviter_id, db)
        if not member or member.role != "owner" or not team:
            raise PermissionDeniedError("只有团队管理员可以发出邀请")
        invitee = (await db.execute(
            select(User).where(User.username == data.username.strip())
        )).scalar_one_or_none()
        if invitee is None:
            raise UserNotFoundError()
        if invitee.id == inviter_id:
            raise InvitationAlreadyExistsError("不能邀请自己")
        existing_member = (await db.execute(
            select(TeamMember).where(TeamMember.user_id == invitee.id)
        )).scalar_one_or_none()
        if existing_member:
            raise AlreadyInTeamError()
        existing = (await db.execute(
            select(TeamInvitation).where(
                TeamInvitation.team_id == team.id,
                TeamInvitation.invitee_id == invitee.id,
                TeamInvitation.status == "pending",
            )
        )).scalar_one_or_none()
        if existing:
            raise InvitationAlreadyExistsError()
        invitation = TeamInvitation(
            team_id=team.id, inviter_id=inviter_id, invitee_id=invitee.id, status="pending"
        )
        db.add(invitation)
        await db.flush()
        return await AuthService._invitation_out(invitation, db)

    @staticmethod
    async def list_invitations(user_id: int, db: AsyncSession) -> list[TeamInvitationOut]:
        """管理员查看本团队邀请，未入组采购员查看发给自己的邀请。"""
        member, team = await AuthService._team_membership(user_id, db)
        if member and team and member.role == "owner":
            stmt = select(TeamInvitation).where(TeamInvitation.team_id == team.id)
        else:
            stmt = select(TeamInvitation).where(
                TeamInvitation.invitee_id == user_id,
                TeamInvitation.status == "pending",
            )
        rows = (await db.execute(stmt.order_by(TeamInvitation.created_at.desc()))).scalars().all()
        return [await AuthService._invitation_out(row, db) for row in rows]

    @staticmethod
    async def respond_invitation(
        user_id: int, invitation_id: int, accepted: bool, db: AsyncSession
    ) -> Token | None:
        """采购员接受或拒绝邀请；接受后签发带团队信息的新 Token。"""
        invitation = (await db.execute(
            select(TeamInvitation).where(
                TeamInvitation.id == invitation_id,
                TeamInvitation.invitee_id == user_id,
                TeamInvitation.status == "pending",
            )
        )).scalar_one_or_none()
        if invitation is None:
            raise InvitationNotFoundError()
        invitation.status = "accepted" if accepted else "rejected"
        if not accepted:
            await db.flush()
            return None
        existing = (await db.execute(
            select(TeamMember).where(TeamMember.user_id == user_id)
        )).scalar_one_or_none()
        if existing:
            raise AlreadyInTeamError()
        db.add(TeamMember(team_id=invitation.team_id, user_id=user_id, role="member"))
        await db.flush()
        user = await db.get(User, user_id)
        return await AuthService._token_for_user(user, db)

    @staticmethod
    async def _invitation_out(invitation: TeamInvitation, db: AsyncSession) -> TeamInvitationOut:
        """将邀请 ORM 转为前端可展示的完整信息。"""
        team = await db.get(Team, invitation.team_id)
        inviter = await db.get(User, invitation.inviter_id)
        invitee = await db.get(User, invitation.invitee_id)
        return TeamInvitationOut(
            invitation_id=invitation.id,
            team_id=invitation.team_id,
            team_name=team.name if team else "",
            inviter_username=inviter.username if inviter else "",
            invitee_username=invitee.username if invitee else "",
            status=invitation.status,
            created_at=invitation.created_at,
        )
