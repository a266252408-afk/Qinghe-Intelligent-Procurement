"""待确认路由决策服务 — 复用消息 metadata 持久化低置信度选择。

不建新表：待确认状态写在 assistant 消息的 metadata_json 中，
结构化数据沿既有 structured_type / structured_data 约定。
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    RouteDecisionExpiredError,
    RouteDecisionNotFoundError,
    RouteDecisionResolvedError,
)
from app.models.knowledge import ConversationSession, Message
from app.schemas.knowledge import MessageOut
from app.schemas.router import ACTIVE_INTENTS, PendingRoute, RouteOption
from app.services.knowledge_base import KnowledgeBaseManager

logger = logging.getLogger(__name__)


class RouteDecisionService:
    """读取、校验、关闭待人工确认的路由决策。"""

    @staticmethod
    async def get_pending(
        session_id: int,
        user_id: int,
        token: str,
        db: AsyncSession,
    ) -> PendingRoute:
        """按 token 查找待确认决策；校验会话归属、状态与有效期。"""
        await KnowledgeBaseManager.ensure_session_owned(session_id, user_id, db)
        stmt = (
            select(Message)
            .where(Message.session_id == session_id, Message.role == "assistant")
            .order_by(Message.id.desc())
        )
        messages = (await db.execute(stmt)).scalars().all()
        for message in messages:
            data = _structured_data(message)
            if data.get("token") != token:
                continue
            if data.get("status", "pending") != "pending":
                raise RouteDecisionResolvedError()
            if _is_expired(data):
                raise RouteDecisionExpiredError()
            return _to_pending(message, data)
        raise RouteDecisionNotFoundError()

    @staticmethod
    async def mark_resolved(
        message_id: int,
        chosen_intent: str,
        cancelled: bool,
        user_id: int,
        db: AsyncSession,
    ) -> None:
        """把待确认消息标记为已处理/已取消；重复提交返回 409。"""
        stmt = (
            select(Message)
            .join(ConversationSession, Message.session_id == ConversationSession.id)
            .where(Message.id == message_id, ConversationSession.user_id == user_id)
        )
        message = (await db.execute(stmt)).scalar_one_or_none()
        if message is None:
            raise RouteDecisionNotFoundError()

        metadata = dict(message.metadata_json or {})
        data = dict(metadata.get("structured_data") or {})
        if data.get("status", "pending") != "pending":
            raise RouteDecisionResolvedError()

        data["status"] = "cancelled" if cancelled else "resolved"
        data["chosen_intent"] = chosen_intent
        data["resolved_at"] = datetime.now(timezone.utc).isoformat()
        metadata["structured_data"] = data
        # 赋新字典，确保 SQLAlchemy 检测到 JSON 字段变更
        message.metadata_json = metadata
        db.add(message)
        await db.flush()

    @staticmethod
    async def get_history_before(
        session_id: int,
        user_id: int,
        before_message_id: int,
        db: AsyncSession,
    ) -> list[MessageOut]:
        """取原始用户消息之前的历史，续跑时避免重复拼接当前问题。"""
        await KnowledgeBaseManager.ensure_session_owned(session_id, user_id, db)
        stmt = (
            select(Message)
            .where(Message.session_id == session_id, Message.id < before_message_id)
            .order_by(Message.id)
        )
        messages = (await db.execute(stmt)).scalars().all()
        return [
            MessageOut(
                message_id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                metadata=m.metadata_json,
                created_at=m.created_at,
            )
            for m in messages
        ]


def _structured_data(message: Message) -> dict:
    """提取 route_confirm 的 structured_data；非目标消息返回空字典。"""
    metadata = message.metadata_json or {}
    if metadata.get("structured_type") != "route_confirm":
        return {}
    data = metadata.get("structured_data")
    return data if isinstance(data, dict) else {}


def _is_expired(data: dict) -> bool:
    """按 created_at + ttl_minutes 判断是否过期；无时间戳的旧数据不过期。"""
    raw = data.get("created_at")
    if not raw:
        return False
    try:
        created = datetime.fromisoformat(str(raw))
    except ValueError:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    ttl = int(data.get("ttl_minutes") or settings.ROUTE_CONFIRM_TTL_MINUTES)
    return datetime.now(timezone.utc) > created + timedelta(minutes=ttl)


def _to_pending(message: Message, data: dict) -> PendingRoute:
    """把 metadata 还原为 PendingRoute；字段缺失时抛 404 而非 500。"""
    try:
        user_message_id = int(data["user_message_id"])
        # 过滤已下线意图（例如旧 payload 中的 knowledge_record）
        options = [
            RouteOption(**item)
            for item in (data.get("options") or [])
            if item.get("intent") in ACTIVE_INTENTS
        ]
        return PendingRoute(
            message_id=message.id,
            session_id=message.session_id,
            token=str(data["token"]),
            message=str(data["message"]),
            file_id=data.get("file_id"),
            file_type=data.get("file_type"),
            file_name=data.get("file_name"),
            upload_id=data.get("upload_id"),
            user_message_id=user_message_id,
            options=options,
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("路由确认 metadata 不完整：%s", exc)
        raise RouteDecisionNotFoundError() from exc
