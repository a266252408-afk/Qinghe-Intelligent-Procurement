"""低置信度路由 Hook 与人工确认 payload 测试。"""
import pytest

from app.agents.route_hooks import (
    ManualConfirmationHook,
    RouteHookContext,
    build_confirm_payload,
)
from app.schemas.router import RouteResult


def _route(
    intent: str = "chat",
    confidence: float = 0.4,
    source: str = "jev",
    needs_confirmation: bool = True,
    probabilities: dict | None = None,
) -> RouteResult:
    return RouteResult(
        intent=intent,  # type: ignore[arg-type]
        target_agent="ChatAgent",
        confidence=confidence,
        source=source,
        needs_confirmation=needs_confirmation,
        probabilities=probabilities if probabilities is not None else {
            "chat": 0.4, "parse_list": 0.25, "compare": 0.15,
            "parse_quote": 0.08, "knowledge_query": 0.06,
            "generate_inquiry": 0.02,
        },
    )


def _ctx(route: RouteResult, file_type: str | None = None) -> RouteHookContext:
    return RouteHookContext(
        message="香樟怎么处理", session_id=1, user_id=2, team_id=3,
        route=route, has_file=bool(file_type), file_type=file_type,
        file_id="file-1" if file_type else None,
    )


@pytest.mark.asyncio
async def test_low_confidence_jev_triggers_confirm():
    result = await ManualConfirmationHook()(_ctx(_route()))
    assert result.action == "confirm"


@pytest.mark.asyncio
@pytest.mark.parametrize("route", [
    _route(confidence=0.9, needs_confirmation=False),
    _route(source="rule", needs_confirmation=False),
    _route(source="light_llm", needs_confirmation=False),
])
async def test_high_confidence_or_rule_does_not_confirm(route):
    result = await ManualConfirmationHook()(_ctx(route))
    assert result.action == "continue"


@pytest.mark.asyncio
async def test_fallback_light_llm_low_confidence_triggers_confirm():
    """JEV 降级到轻量模型后仍低置信度，也要人工兜底。"""
    result = await ManualConfirmationHook()(
        _ctx(_route(source="light_llm", confidence=0.4, needs_confirmation=True))
    )
    assert result.action == "confirm"


def test_payload_contains_all_intents_sorted_and_executable_flags():
    """弹窗必须拿到全部 6 类，按概率降序，并标注能否真正执行。"""
    payload = build_confirm_payload(_ctx(_route(), file_type="list"), user_message_id=42)

    assert payload["user_message_id"] == 42
    assert payload["status"] == "pending"
    assert payload["token"]
    assert payload["source"] == "jev"
    assert len(payload["options"]) == 6
    probabilities = [item["probability"] for item in payload["options"]]
    assert probabilities == sorted(probabilities, reverse=True)

    by_intent = {item["intent"]: item for item in payload["options"]}
    assert "knowledge_record" not in by_intent
    assert by_intent["parse_list"]["executable"] is True
    assert by_intent["parse_quote"]["executable"] is False
    assert "报价单" in by_intent["parse_quote"]["note"]
    assert by_intent["knowledge_query"]["executable"] is True
    assert by_intent["chat"]["executable"] is True
    assert "仅提示" in by_intent["compare"]["note"]


def test_payload_prefers_suggested_intent_when_probabilities_empty():
    """轻量模型降级没有概率分布时，模型建议意图仍排第一。"""
    route = _route(
        intent="knowledge_query", source="light_llm",
        confidence=0.5, needs_confirmation=True, probabilities={},
    )
    payload = build_confirm_payload(_ctx(route), user_message_id=1)
    assert payload["options"][0]["intent"] == "knowledge_query"


def test_payload_marks_parse_unavailable_without_file():
    payload = build_confirm_payload(_ctx(_route()), user_message_id=1)
    by_intent = {item["intent"]: item for item in payload["options"]}
    assert by_intent["parse_list"]["executable"] is False
    assert "采购清单" in by_intent["parse_list"]["note"]
