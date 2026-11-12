"""ChatInput 待确认续跑字段校验。"""
import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatInput


def test_pending_token_requires_forced_intent():
    with pytest.raises(ValidationError):
        ChatInput(message="x", session_id=1, pending_token="tok")


def test_route_cancelled_requires_chat_and_token():
    with pytest.raises(ValidationError):
        ChatInput(
            message="x", session_id=1, pending_token="tok",
            forced_intent="parse_list", route_cancelled=True,
        )
    with pytest.raises(ValidationError):
        ChatInput(message="x", session_id=1, forced_intent="chat", route_cancelled=True)


def test_removed_knowledge_record_is_rejected():
    """knowledge_record 已从活跃意图删除，续跑字段也必须拒绝。"""
    with pytest.raises(ValidationError):
        ChatInput(
            message="x", session_id=1, pending_token="tok",
            forced_intent="knowledge_record",
        )


def test_valid_continuation_payload():
    data = ChatInput(
        message="x", session_id=1, pending_token="tok",
        forced_intent="chat", route_cancelled=True,
    )
    assert data.forced_intent == "chat"
    assert data.route_cancelled is True
