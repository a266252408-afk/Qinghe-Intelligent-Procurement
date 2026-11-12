"""ChatAgent 低置信度确认帧与人工选择续跑测试。"""
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage
from sqlalchemy import select

from app.agents.chat import ChatAgent
from app.agents.router import RouterAgent
from app.models.knowledge import ConversationSession, Message
from app.models.user import User
from app.schemas.chat import ChatInput
from app.schemas.router import RouteResult
from app.services.llm_factory import LLMFactory

pytestmark = pytest.mark.asyncio


class FakeMediumLLM:
    """记录输入消息的假中量模型。"""

    def __init__(self):
        self.stream_messages = None

    async def astream(self, messages):
        self.stream_messages = messages
        yield AIMessageChunk(content="好的，已按你的选择处理。")


def _low_confidence_route() -> RouteResult:
    return RouteResult(
        intent="chat",
        target_agent="ChatAgent",
        confidence=0.42,
        source="jev",
        needs_confirmation=True,
        probabilities={
            "chat": 0.42, "parse_list": 0.24, "compare": 0.14,
            "parse_quote": 0.08, "knowledge_query": 0.06,
            "generate_inquiry": 0.02,
        },
    )


async def _setup(db):
    user = User(username="chat-user", password_hash="x")
    db.add(user)
    await db.flush()
    session = ConversationSession(user_id=user.id, title="test")
    db.add(session)
    await db.flush()
    return user, session


async def _messages(db, session_id: int) -> list[Message]:
    stmt = select(Message).where(Message.session_id == session_id).order_by(Message.id)
    return list((await db.execute(stmt)).scalars().all())


async def _create_pending(db, monkeypatch) -> tuple[User, ConversationSession, dict]:
    """触发一次低置信度路由，返回用户、会话和确认 payload。"""
    user, session = await _setup(db)
    monkeypatch.setattr(
        RouterAgent, "route",
        AsyncMock(return_value=_low_confidence_route()),
    )
    chunks = [
        chunk async for chunk in ChatAgent().chat_stream(
            ChatInput(message="香樟怎么处理", session_id=session.id), user.id, 1, db
        )
    ]
    confirm = [chunk for chunk in chunks if chunk.type == "route_confirm"]
    assert len(confirm) == 1
    return user, session, confirm[0].data


async def test_low_confidence_emits_confirm_frame_and_persists(db, monkeypatch):
    user, session, payload = await _create_pending(db, monkeypatch)

    assert payload["status"] == "pending"
    assert payload["confidence"] == 0.42
    assert len(payload["options"]) == 6
    assert payload["user_message_id"]

    messages = await _messages(db, session.id)
    assert [m.role for m in messages] == ["user", "assistant"]
    stored = messages[-1].metadata_json
    assert stored["structured_type"] == "route_confirm"
    assert stored["structured_data"]["token"] == payload["token"]
    assert stored["structured_data"]["user_message_id"] == messages[0].id


async def test_continuation_skips_duplicate_user_and_resolves(db, monkeypatch):
    user, session, payload = await _create_pending(db, monkeypatch)
    # 续跑不应再次调用路由器
    monkeypatch.setattr(RouterAgent, "route", AsyncMock(side_effect=AssertionError("不应重新路由")))
    fake_llm = FakeMediumLLM()
    monkeypatch.setattr(LLMFactory, "get_medium", staticmethod(lambda: fake_llm))

    chunks = [
        chunk async for chunk in ChatAgent().chat_stream(
            ChatInput(
                message="客户端回传的旧消息", session_id=session.id,
                forced_intent="chat", pending_token=payload["token"],
            ),
            user.id, 1, db,
        )
    ]

    assert any("已按你的选择处理" in chunk.delta for chunk in chunks)
    messages = await _messages(db, session.id)
    assert [m.role for m in messages] == ["user", "assistant", "assistant"]
    assert sum(1 for m in messages if m.role == "user") == 1
    assert messages[1].metadata_json["structured_data"]["status"] == "resolved"
    assert messages[1].metadata_json["structured_data"]["chosen_intent"] == "chat"

    human_messages = [m for m in fake_llm.stream_messages if isinstance(m, HumanMessage)]
    assert [m.content for m in human_messages] == ["香樟怎么处理"]


async def test_cancel_continues_as_chat_and_marks_cancelled(db, monkeypatch):
    user, session, payload = await _create_pending(db, monkeypatch)
    monkeypatch.setattr(LLMFactory, "get_medium", staticmethod(lambda: FakeMediumLLM()))

    chunks = [
        chunk async for chunk in ChatAgent().chat_stream(
            ChatInput(
                message="ignored", session_id=session.id,
                forced_intent="chat", pending_token=payload["token"],
                route_cancelled=True,
            ),
            user.id, 1, db,
        )
    ]

    assert chunks[-1].done is True
    messages = await _messages(db, session.id)
    assert messages[1].metadata_json["structured_data"]["status"] == "cancelled"


async def test_manual_parse_without_file_returns_guidance(db, monkeypatch):
    user, session, payload = await _create_pending(db, monkeypatch)
    # 该分支不应调用模型
    monkeypatch.setattr(
        LLMFactory, "get_medium",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("不应调用模型"))),
    )

    chunks = [
        chunk async for chunk in ChatAgent().chat_stream(
            ChatInput(
                message="ignored", session_id=session.id,
                forced_intent="parse_list", pending_token=payload["token"],
            ),
            user.id, 1, db,
        )
    ]

    assert "请先上传采购清单文件" in "".join(chunk.delta for chunk in chunks)
    messages = await _messages(db, session.id)
    assert [m.role for m in messages] == ["user", "assistant", "assistant"]
    assert messages[1].metadata_json["structured_data"]["status"] == "resolved"


async def test_repeated_choice_is_rejected(db, monkeypatch):
    user, session, payload = await _create_pending(db, monkeypatch)
    monkeypatch.setattr(LLMFactory, "get_medium", staticmethod(lambda: FakeMediumLLM()))

    request = ChatInput(
        message="ignored", session_id=session.id,
        forced_intent="chat", pending_token=payload["token"],
    )
    _ = [chunk async for chunk in ChatAgent().chat_stream(request, user.id, 1, db)]
    second = [
        chunk async for chunk in ChatAgent().chat_stream(request, user.id, 1, db)
    ]

    assert "已处理" in "".join(chunk.delta for chunk in second)
