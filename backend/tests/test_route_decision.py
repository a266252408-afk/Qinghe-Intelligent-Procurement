"""待确认路由决策服务测试。"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import (
    RouteDecisionExpiredError,
    RouteDecisionNotFoundError,
    RouteDecisionResolvedError,
)
from app.models.knowledge import ConversationSession, Message
from app.models.user import User
from app.services.route_decision import RouteDecisionService

pytestmark = pytest.mark.asyncio


async def _setup(db):
    """创建用户、会话和一条待确认 assistant 消息。"""
    user = User(username="route-user", password_hash="x")
    db.add(user)
    await db.flush()
    session = ConversationSession(user_id=user.id, title="test")
    db.add(session)
    await db.flush()
    return user, session


async def _add_confirm(
    db,
    session_id: int,
    token: str = "tok-1",
    status: str = "pending",
    created_at: datetime | None = None,
    user_message_id: int = 1,
) -> Message:
    message = Message(
        session_id=session_id,
        role="assistant",
        content="请确认路由",
        created_at=created_at or datetime.now(timezone.utc),
        metadata_json={
            "structured_type": "route_confirm",
            "structured_data": {
                "status": status,
                "token": token,
                "message": "香樟怎么处理",
                "has_file": False,
                "file_type": None,
                "user_message_id": user_message_id,
                "jev_intent": "chat",
                "confidence": 0.4,
                "threshold": 0.6,
                "probabilities": {"chat": 0.4},
                "options": [{
                    "intent": "chat",
                    "label": "普通对话",
                    "description": "按通用对话回答",
                    "probability": 0.4,
                    "executable": True,
                    "note": None,
                }],
                "created_at": (created_at or datetime.now(timezone.utc)).isoformat(),
                "ttl_minutes": 30,
            },
        },
    )
    db.add(message)
    await db.flush()
    return message


async def test_get_pending_returns_original_message(db):
    user, session = await _setup(db)
    await _add_confirm(db, session.id, user_message_id=99)

    pending = await RouteDecisionService.get_pending(
        session.id, user.id, "tok-1", db
    )

    assert pending.message == "香樟怎么处理"
    assert pending.user_message_id == 99
    assert pending.options[0].intent == "chat"


async def test_get_pending_not_found(db):
    user, session = await _setup(db)
    await _add_confirm(db, session.id)
    with pytest.raises(RouteDecisionNotFoundError):
        await RouteDecisionService.get_pending(session.id, user.id, "missing", db)


async def test_get_pending_expired(db):
    user, session = await _setup(db)
    old = datetime.now(timezone.utc) - timedelta(minutes=31)
    await _add_confirm(db, session.id, created_at=old)

    with pytest.raises(RouteDecisionExpiredError):
        await RouteDecisionService.get_pending(session.id, user.id, "tok-1", db)


async def test_get_pending_already_resolved(db):
    user, session = await _setup(db)
    await _add_confirm(db, session.id, status="resolved")

    with pytest.raises(RouteDecisionResolvedError):
        await RouteDecisionService.get_pending(session.id, user.id, "tok-1", db)


async def test_mark_resolved_updates_metadata_and_rejects_repeat(db):
    user, session = await _setup(db)
    message = await _add_confirm(db, session.id)

    await RouteDecisionService.mark_resolved(
        message.id, "chat", cancelled=False, user_id=user.id, db=db
    )

    stored = await db.get(Message, message.id)
    data = stored.metadata_json["structured_data"]
    assert data["status"] == "resolved"
    assert data["chosen_intent"] == "chat"
    assert data["resolved_at"]

    with pytest.raises(RouteDecisionResolvedError):
        await RouteDecisionService.mark_resolved(
            message.id, "chat", cancelled=False, user_id=user.id, db=db
        )


async def test_mark_resolved_cancelled(db):
    user, session = await _setup(db)
    message = await _add_confirm(db, session.id)

    await RouteDecisionService.mark_resolved(
        message.id, "chat", cancelled=True, user_id=user.id, db=db
    )

    stored = await db.get(Message, message.id)
    assert stored.metadata_json["structured_data"]["status"] == "cancelled"


async def test_history_before_excludes_original_question(db):
    user, session = await _setup(db)
    first = Message(session_id=session.id, role="user", content="更早的问题")
    db.add(first)
    await db.flush()
    original = Message(session_id=session.id, role="user", content="香樟怎么处理")
    db.add(original)
    await db.flush()

    history = await RouteDecisionService.get_history_before(
        session.id, user.id, original.id, db
    )

    assert [item.content for item in history] == ["更早的问题"]
