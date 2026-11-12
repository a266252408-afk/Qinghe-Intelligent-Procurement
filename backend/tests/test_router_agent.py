"""路由 Agent 测试：JEV 主路由、规则/轻量模型降级与低置信度标记。"""
import pytest
from unittest.mock import AsyncMock, patch

from app.agents.router import RouterAgent
from app.core.config import settings
from app.core.exceptions import LLMUnavailableError
from app.schemas.router import RouteResult, RouterInput
from app.services.llm_factory import LLMFactory


pytestmark = pytest.mark.asyncio


async def test_rule_route_list_file(db):
    """有采购清单文件时，直接路由到 ListParserAgent"""
    agent = RouterAgent()
    result = await agent.route(
        RouterInput(message="这是清单", has_file=True, file_type="list"),
        team_id=1,
        db=db,
    )
    assert result.intent == "parse_list"
    assert result.target_agent == "ListParserAgent"
    assert result.confidence == 1.0


async def test_rule_route_quote_file(db):
    """有报价单文件时，直接路由到 QuoteParseAgent"""
    agent = RouterAgent()
    result = await agent.route(
        RouterInput(message="这是报价", has_file=True, file_type="quote"),
        team_id=1,
        db=db,
    )
    assert result.intent == "parse_quote"
    assert result.target_agent == "QuoteParseAgent"


async def test_llm_route_fallback_on_error(db):
    """_llm_route 抛异常时 route() 不捕获，直接向上传播（规则路由外无降级包装）"""
    agent = RouterAgent()
    fallback = RouteResult(intent="chat", target_agent="ChatAgent", confidence=0.5)

    # 模拟 _llm_route 内部失败：patch _llm_route 方法，使其返回降级结果
    with patch.object(agent, "_llm_route", new=AsyncMock(return_value=fallback)):
        result = await agent.route(
            RouterInput(message="你好"),
            team_id=1,
            db=db,
        )
    assert result.intent == "chat"
    assert result.target_agent == "ChatAgent"


async def test_slash_commands_use_deterministic_routes(db):
    """斜杠命令不应调用 LLM，直接返回对应 Agent。"""
    agent = RouterAgent()
    for message, intent, target in [
        ("/历史 香樟", "chat", "ChatAgent"),
        ("/知识 验收规范", "knowledge_query", "KnowledgeAgent"),
        ("/询价", "generate_inquiry", "InquiryAgent"),
        ("/比价", "compare", "CompareAgent"),
    ]:
        result = await agent.route(
            RouterInput(message=message, session_id="1"),
            team_id=1,
            db=db,
        )
        assert (result.intent, result.target_agent) == (intent, target)


async def test_material_history_questions_route_to_chat_agent(db):
    """材料历史价格问题交给 ChatAgent，由其按需调用长期记忆工具。"""
    for message in ("银杏的历史成交价", "香樟上次买多少钱", "以前报价有吗"):
        result = await RouterAgent().route(
            RouterInput(message=message, session_id="1"), team_id=1, db=db
        )
        assert (result.intent, result.target_agent) == ("chat", "ChatAgent")


async def test_english_history_command_routes_to_chat_agent(db):
    """英文历史命令也交给 ChatAgent。"""
    result = await RouterAgent().route(
        RouterInput(message="/history ginkgo", session_id="1"), team_id=1, db=db
    )
    assert (result.intent, result.target_agent) == ("chat", "ChatAgent")


# ── JEV 主路由 / 降级 ─────────────────────────────────────────────────────

class FakeJevClient:
    """可注入成功响应或异常的 JEV 假客户端。"""

    def __init__(self, payload: dict | None = None, error: Exception | None = None):
        self.payload = payload
        self.error = error
        self.calls = []

    async def judge(self, state: dict, questions: dict) -> dict:
        self.calls.append((state, questions))
        if self.error:
            raise self.error
        return self.payload or {}


def _enable_jev(monkeypatch, client: FakeJevClient) -> None:
    monkeypatch.setattr(settings, "JEV_ENABLED", True)
    monkeypatch.setattr(settings, "JEV_API_KEY", "test-key")
    monkeypatch.setattr(LLMFactory, "get_jev", staticmethod(lambda: client))


def _jev_payload(intent: str, confidence: float) -> dict:
    probabilities = {intent: confidence}
    if intent != "chat":
        probabilities["chat"] = max(0.0, 1 - confidence)
    return {
        "model": "jev-1.13.0",
        "answers": {"intent": {
            "type": "choice",
            "choice": intent,
            "confidence": confidence,
            "probabilities": probabilities,
        }},
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }


async def test_jev_is_primary_even_with_attachment(db, monkeypatch):
    """有附件时也先问 JEV；规则层只在 JEV 故障后启用。"""
    client = FakeJevClient(_jev_payload("compare", 0.9))
    _enable_jev(monkeypatch, client)

    result = await RouterAgent().route(
        RouterInput(message="这是清单", has_file=True, file_type="list"), 1, db
    )

    assert (result.intent, result.source) == ("compare", "jev")
    assert result.needs_confirmation is False
    assert len(client.calls) == 1


async def test_jev_instructions_include_query_scope_guide(db, monkeypatch):
    """JEV 请求里必须带上长期材料记忆 vs 行业知识库的区分口径。"""
    client = FakeJevClient(_jev_payload("chat", 0.9))
    _enable_jev(monkeypatch, client)

    await RouterAgent().route(RouterInput(message="香樟怎么养护"), 1, db)

    instructions = client.calls[0][1]["intent"]["instructions"]
    assert "长期材料记忆 vs 行业知识库" in instructions
    assert "香樟上次买多少钱" in instructions
    assert "香樟树苗怎么养护" in instructions


async def test_low_confidence_jev_falls_back_to_rules(db, monkeypatch):
    """JEV 低置信度先走规则降级；历史价格问题由规则确定，不再弹窗。"""
    _enable_jev(monkeypatch, FakeJevClient(_jev_payload("chat", 0.42)))
    result = await RouterAgent().route(
        RouterInput(message="香樟上次买多少钱"), 1, db
    )
    assert (result.intent, result.source) == ("chat", "rule")
    assert result.needs_confirmation is False


async def test_low_confidence_jev_then_llm_low_confidence_needs_confirmation(db, monkeypatch):
    """JEV 与轻量模型都不确定时，才进入人工确认。"""
    _enable_jev(monkeypatch, FakeJevClient(_jev_payload("chat", 0.42)))
    agent = RouterAgent()
    monkeypatch.setattr(agent, "_llm_route", AsyncMock(return_value=RouteResult(
        intent="chat", target_agent="ChatAgent", confidence=0.5,
        source="light_llm", needs_confirmation=True,
    )))

    result = await agent.route(RouterInput(message="这个怎么办"), 1, db)

    assert result.source == "light_llm"
    assert result.needs_confirmation is True


async def test_low_confidence_jev_then_llm_high_confidence_executes(db, monkeypatch):
    """降级模型高置信度时直接执行，不打扰用户。"""
    _enable_jev(monkeypatch, FakeJevClient(_jev_payload("chat", 0.42)))
    agent = RouterAgent()
    monkeypatch.setattr(agent, "_llm_route", AsyncMock(return_value=RouteResult(
        intent="knowledge_query", target_agent="KnowledgeAgent", confidence=0.9,
        source="light_llm", needs_confirmation=False,
    )))

    result = await agent.route(RouterInput(message="香樟怎么养护"), 1, db)

    assert result.intent == "knowledge_query"
    assert result.needs_confirmation is False


async def test_jev_failure_falls_back_to_rules(db, monkeypatch):
    """JEV 超时/5xx 后静默回退到附件规则。"""
    _enable_jev(monkeypatch, FakeJevClient(error=LLMUnavailableError("down")))
    result = await RouterAgent().route(
        RouterInput(message="这是清单", has_file=True, file_type="list"), 1, db
    )
    assert (result.intent, result.source) == ("parse_list", "rule")
    assert result.needs_confirmation is False


async def test_jev_failure_without_rule_falls_back_to_light_llm(db, monkeypatch):
    """规则未命中时继续降级到轻量模型。"""
    _enable_jev(monkeypatch, FakeJevClient(error=LLMUnavailableError("down")))
    agent = RouterAgent()
    monkeypatch.setattr(agent, "_llm_route", AsyncMock(return_value=RouteResult(
        intent="chat", target_agent="ChatAgent", confidence=0.8, source="light_llm",
    )))

    result = await agent.route(RouterInput(message="帮我写一首诗"), 1, db)

    assert (result.intent, result.source) == ("chat", "light_llm")
    assert result.needs_confirmation is False


async def test_invalid_jev_choice_falls_back(db, monkeypatch):
    """JEV 返回未知意图时按协议错误降级，不把非法意图传给下游。"""
    _enable_jev(monkeypatch, FakeJevClient(_jev_payload("unknown", 0.9)))
    agent = RouterAgent()
    monkeypatch.setattr(agent, "_llm_route", AsyncMock(return_value=RouteResult(
        intent="chat", target_agent="ChatAgent", confidence=0.8, source="light_llm",
    )))

    result = await agent.route(RouterInput(message="帮我写一首诗"), 1, db)

    assert result.intent == "chat"
    assert result.source == "light_llm"
