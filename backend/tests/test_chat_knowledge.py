"""ChatAgent 行业知识问答分发测试。"""
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.agents.chat import ChatAgent
from app.agents.router import RouterAgent
from app.models.knowledge import ConversationSession, Message
from app.models.user import User
from app.schemas.chat import ChatInput
from app.schemas.knowledge import SearchResult
from app.schemas.knowledge_agent import KnowledgeQueryResult
from app.schemas.router import RouteResult

pytestmark = pytest.mark.asyncio


async def _setup(db):
    user = User(username="knowledge-user", password_hash="x")
    db.add(user)
    await db.flush()
    session = ConversationSession(user_id=user.id, title="test")
    db.add(session)
    await db.flush()
    return user, session


def _knowledge_route() -> RouteResult:
    return RouteResult(
        intent="knowledge_query",
        target_agent="KnowledgeAgent",
        confidence=0.9,
        source="jev",
    )


async def test_knowledge_query_calls_agent_and_emits_frame(db, monkeypatch):
    user, session = await _setup(db)
    monkeypatch.setattr(RouterAgent, "route", AsyncMock(return_value=_knowledge_route()))
    query = AsyncMock(return_value=KnowledgeQueryResult(
        answer="香樟养护应保持土壤湿润。\n\n依据：养护手册.pdf",
        sources=["industry"],
        results=[SearchResult(
            source="industry", source_file="养护手册.pdf",
            content="香樟养护要点", score=0.9,
        )],
    ))
    monkeypatch.setattr("app.agents.chat_knowledge.KnowledgeAgent.query", query)

    chunks = [
        chunk async for chunk in ChatAgent().chat_stream(
            ChatInput(message="香樟树苗怎么养护", session_id=session.id),
            user.id, 1, db,
        )
    ]

    knowledge = [chunk for chunk in chunks if chunk.type == "knowledge"]
    assert len(knowledge) == 1
    assert "土壤湿润" in knowledge[0].delta
    assert knowledge[0].data["results"][0]["source_file"] == "养护手册.pdf"
    assert query.await_count == 1

    messages = list((await db.execute(
        select(Message).where(Message.session_id == session.id).order_by(Message.id)
    )).scalars().all())
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[-1].metadata_json["structured_type"] == "knowledge"
    assert messages[-1].metadata_json["structured_data"]["sources"] == ["industry"]


async def test_empty_knowledge_command_returns_hint_without_agent(db, monkeypatch):
    user, session = await _setup(db)
    monkeypatch.setattr(RouterAgent, "route", AsyncMock(return_value=_knowledge_route()))
    query = AsyncMock(side_effect=AssertionError("空问题不应调用知识库"))
    monkeypatch.setattr("app.agents.chat_knowledge.KnowledgeAgent.query", query)

    chunks = [
        chunk async for chunk in ChatAgent().chat_stream(
            ChatInput(message="/知识", session_id=session.id),
            user.id, 1, db,
        )
    ]

    assert "请在 /知识 后写明要查询的问题" in "".join(chunk.delta for chunk in chunks)
    assert query.await_count == 0
