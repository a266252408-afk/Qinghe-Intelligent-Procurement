"""知识库检索回答整理测试。"""
from unittest.mock import AsyncMock

import pytest

from app.agents.knowledge import _NO_RESULT_ANSWER, KnowledgeAgent
from app.schemas.knowledge import SearchResult
from app.schemas.knowledge_agent import KnowledgeQueryInput

pytestmark = pytest.mark.asyncio


class FakeResponse:
    """模拟 LangChain 响应。"""

    def __init__(self, content: str):
        self.content = content


class FakeLLM:
    """模拟中量档模型，记录实际收到的严格依据上下文。"""

    model_name = "test-medium"

    def __init__(self, content: str):
        self.content = content
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> FakeResponse:
        self.prompts.append(prompt)
        return FakeResponse(self.content)


async def test_query_organizes_retrieved_content_and_keeps_evidence(monkeypatch):
    """有检索结果时调用模型，并同时返回整理回答和原始依据。"""
    llm = FakeLLM("园路与铺装工程的相关内容见依据1。\n\n依据：依据1")
    monkeypatch.setattr("app.services.llm_factory.LLMFactory.get_medium", lambda: llm)
    log = AsyncMock()
    monkeypatch.setattr("app.services.llm_logger.LLMCallLogger.log", log)
    monkeypatch.setattr(
        "app.services.knowledge_base.KnowledgeBaseManager.search_industry",
        AsyncMock(return_value=[SearchResult(
            source="industry", source_file="园林施工.pdf", content="园路与铺装工程", score=0.9
        )]),
    )
    history_search = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.services.knowledge_base.KnowledgeBaseManager.search_history",
        history_search,
    )

    result = await KnowledgeAgent().query(
        KnowledgeQueryInput(question="园路与铺装工程", session_id="session-1"),
        team_id=3,
        db=None,
    )

    assert result.answer.startswith("园路与铺装工程")
    assert result.sources == ["industry"]
    assert result.results[0].content == "园路与铺装工程"
    assert result.answer.endswith("依据：园林施工.pdf")
    assert "[依据1]" in llm.prompts[0]
    history_search.assert_not_awaited()
    log.assert_awaited_once()


async def test_query_without_results_does_not_call_llm(monkeypatch):
    """无检索结果时返回明确的无法确认，不调用模型。"""
    monkeypatch.setattr(
        "app.services.knowledge_base.KnowledgeBaseManager.search_industry",
        AsyncMock(return_value=[]),
    )
    history_search = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.services.knowledge_base.KnowledgeBaseManager.search_history",
        history_search,
    )
    get_medium = AsyncMock(side_effect=AssertionError("无结果不应调用模型"))
    monkeypatch.setattr("app.services.llm_factory.LLMFactory.get_medium", get_medium)

    result = await KnowledgeAgent().query(
        KnowledgeQueryInput(question="不存在的内容"), team_id=3, db=None
    )

    assert result.answer == _NO_RESULT_ANSWER
    assert result.results == []
    get_medium.assert_not_awaited()
    history_search.assert_not_awaited()


async def test_query_llm_failure_does_not_fabricate_answer(monkeypatch):
    """模型失败时不提供脱离检索依据的泛化回答。"""
    failing_llm = FakeLLM("")

    async def fail(_prompt: str):
        raise RuntimeError("model unavailable")

    failing_llm.ainvoke = fail
    monkeypatch.setattr("app.services.llm_factory.LLMFactory.get_medium", lambda: failing_llm)
    monkeypatch.setattr("app.services.llm_logger.LLMCallLogger.log", AsyncMock())
    monkeypatch.setattr(
        "app.services.knowledge_base.KnowledgeBaseManager.search_industry",
        AsyncMock(return_value=[SearchResult(source="industry", content="仅有依据", score=0.8)]),
    )
    monkeypatch.setattr(
        "app.services.knowledge_base.KnowledgeBaseManager.search_history",
        AsyncMock(return_value=[]),
    )

    result = await KnowledgeAgent().query(
        KnowledgeQueryInput(question="查询", session_id="session-2"), team_id=3, db=None
    )

    assert result.answer == "模型整理失败，请核对下方检索依据。"
    assert result.results[0].content == "仅有依据"
