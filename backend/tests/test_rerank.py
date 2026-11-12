"""检索重排序（rerank）功能测试：默认关闭、开启生效、失败降级、候选池截断。"""
import pytest

from app.models.knowledge import IndustryKnowledge
from app.services.knowledge_base import KnowledgeBaseManager
from app.services.rerank_client import RerankClient

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clean_retrieval_caches():
    """清空 BM25/LLM 工厂进程级缓存。

    _BM25_CACHE 签名为 (文档数, 最大ID)，内存库每个测试都从 id=1 重建，
    不同测试间签名会撞车导致复用上一测试的索引，必须逐测试清理。
    """
    from app.services import knowledge_base, llm_factory

    knowledge_base._BM25_CACHE.clear()
    llm_factory.LLMFactory._instances.clear()
    yield
    knowledge_base._BM25_CACHE.clear()
    llm_factory.LLMFactory._instances.clear()


def _seed_docs(db) -> list[str]:
    """入库 3 个分块，返回其内容（混排默认顺序下语义块通常靠前）。"""
    contents = [
        "A块：园林工程泛论，与查询无直接语义关联但含关键词灌溉。",
        "B块：灌溉系统施工前必须完成水压试验并冲洗管网。",
        "C块：苗木养护要点，浇水遵循不干不浇浇则浇透。",
    ]
    db.add_all([
        IndustryKnowledge(team_id=3, source_file="3/knowledge/doc.txt", content=c)
        for c in contents
    ])
    return contents


def _stub_rerank(monkeypatch, order: list[int]) -> list[list[str]]:
    """打桩 RerankClient.rerank 按 order 返回下标序列，记录每次调用入参。"""
    calls: list[list[str]] = []

    async def fake_rerank(self, query, documents, top_n=None, **kwargs):
        calls.append(list(documents))
        return [(i, float(len(order) - pos)) for pos, i in enumerate(order)]

    monkeypatch.setattr(RerankClient, "rerank", fake_rerank)
    return calls


def _stub_rerank_by_content(monkeypatch, keyword: str) -> list[list[str]]:
    """打桩 rerank：含 keyword 的文档得高分（与候选列表顺序解耦的确定性排序）。"""
    calls: list[list[str]] = []

    async def fake_rerank(self, query, documents, top_n=None, **kwargs):
        calls.append(list(documents))
        scored = [(i, 1.0 if keyword in d else 0.0) for i, d in enumerate(documents)]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored

    monkeypatch.setattr(RerankClient, "rerank", fake_rerank)
    return calls


async def test_rerank_disabled_by_default(db, monkeypatch):
    """默认（settings.RAG_RERANK_ENABLED=False）不调用 rerank，行为与现状一致。"""
    contents = _seed_docs(db)
    calls = _stub_rerank(monkeypatch, [1, 0, 2])
    results = await KnowledgeBaseManager.search_industry("灌溉", team_id=3, db=db, top_k=2)
    assert calls == []  # 未触发 rerank
    assert results and len(results) <= 2
    assert all(r.content in contents for r in results)


async def test_rerank_reorders_results(db, monkeypatch):
    """开启 rerank 后按客户端打分顺序输出（关闭精确匹配以隔离验证 rerank 排序）。"""
    contents = _seed_docs(db)
    calls = _stub_rerank_by_content(monkeypatch, "苗木养护")  # C 块应被排到第一
    results = await KnowledgeBaseManager.search_industry(
        "灌溉", team_id=3, db=db, top_k=3,
        exact_strategy="off",
        rerank_enabled=True, rerank_candidates=20,
    )
    assert len(calls) == 1
    assert results[0].content == contents[2]  # rerank 排第一的块
    assert len(results) == 3


async def test_rerank_failure_falls_back_to_original_order(db, monkeypatch):
    """rerank 异常时降级：返回混排原序，不抛错不破坏主链路。"""
    _seed_docs(db)

    async def broken_rerank(self, *args, **kwargs):
        raise RuntimeError("rerank API down")

    monkeypatch.setattr(RerankClient, "rerank", broken_rerank)
    results = await KnowledgeBaseManager.search_industry(
        "灌溉", team_id=3, db=db, top_k=3,
        rerank_enabled=True, rerank_candidates=20,
    )
    assert results and len(results) == 3  # 原候选顺序兜底


async def test_rerank_candidates_pool_smaller_than_topk_is_bumped(db, monkeypatch):
    """候选池小于 top_k 时自动抬升到 top_k，保证可返回足量条数。"""
    contents = _seed_docs(db)
    calls = _stub_rerank(monkeypatch, [0, 1, 2])
    await KnowledgeBaseManager.search_industry(
        "灌溉", team_id=3, db=db, top_k=3,
        rerank_enabled=True, rerank_candidates=2,  # < top_k
    )
    assert len(calls) == 1
    assert len(calls[0]) >= 3  # 池被抬升后候选完整


async def test_rerank_client_unconfigured_returns_empty():
    """未配置 API key 的客户端直接空跑返回 []（调用方保持原序）。"""
    client = RerankClient(model="m", base_url="http://localhost:1", api_key="", timeout_s=1)
    assert await client.rerank("q", ["a", "b"]) == []
