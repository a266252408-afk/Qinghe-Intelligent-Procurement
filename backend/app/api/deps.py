"""FastAPI 依赖注入：当前用户、数据库会话、团队 ID 提取"""
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidTokenError
from app.core.security import decode_token
from app.db.session import get_db
from app.schemas.auth import UserInfo


async def get_current_user(
    authorization: str = Header(..., description="Bearer <token>"),
    db: AsyncSession = Depends(get_db),
) -> UserInfo:
    """从请求头提取并校验 JWT，返回当前用户信息

    认证查询后立即提交：结束读事务并归还连接快照。SQLite WAL 下
    "先读后写"的事务在升级写锁时会立即报 database is locked（不走
    busy_timeout 等待），认证读是每个请求的第一段读，尽早释放可
    大幅缩小后续业务写与读快照的冲突窗口。
    """
    if not authorization.startswith("Bearer "):
        raise InvalidTokenError()
    token = authorization.removeprefix("Bearer ")
    payload = decode_token(token)
    from app.services.auth_service import AuthService
    user = await AuthService.get_current_user(payload["user_id"], db)
    await db.commit()
    return user


async def get_team_id(current_user: UserInfo = Depends(get_current_user)) -> int:
    """提取并校验 team_id；未加入团队时抛出 403"""
    from app.core.exceptions import PermissionDeniedError
    if current_user.team_id is None:
        raise PermissionDeniedError("请先加入或创建团队")
    return current_user.team_id
