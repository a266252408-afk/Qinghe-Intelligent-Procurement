"""行业知识库精确短语优先检索测试。"""
import pytest

from app.models.knowledge import IndustryKnowledge
from app.services.knowledge_base import KnowledgeBaseManager, _source_file_name

pytestmark = pytest.mark.asyncio


async def test_old_generated_storage_name_has_explicit_fallback_label():
    """历史数据没有原始文件名时，不向用户展示 UUID。"""
    assert _source_file_name("3/knowledge/2026/08/" + "a" * 32 + ".pdf") == "历史上传文档（原始文件名未记录）"


async def test_bm25_cache_rebuilds_when_max_rowid_is_reused(db, monkeypatch):
    """删除最大分块后重新入库（SQLite 复用 rowid）时，BM25 缓存必须失效重建。

    旧签名 (文档数, 最大ID) 在"删除 id=3 再插入新分块复用 id=3"时完全不变，
    会继续命中旧语料，导致新上传内容检索不到。
    """
    from langchain_community.retrievers import BM25Retriever

    from app.services import knowledge_base

    knowledge_base._BM25_CACHE.clear()
    old_docs = [
        IndustryKnowledge(team_id=3, source_file="doc.txt", content="旧分块：灌溉系统施工。"),
        IndustryKnowledge(team_id=3, source_file="doc.txt", content="旧分块：苗木修剪。"),
        IndustryKnowledge(team_id=3, source_file="doc.txt", content="旧分块：土壤改良。"),
    ]
    db.add_all(old_docs)
    await db.flush()
    assert [doc.id for doc in old_docs] == [1, 2, 3]

    def fail_vector_search(_collection: str):
        raise RuntimeError("test uses BM25 fallback")

    monkeypatch.setattr(knowledge_base, "_get_chroma", fail_vector_search)

    builds: list[int] = []
    original_from_documents = BM25Retriever.from_documents

    def counting_from_documents(cls, documents, **kwargs):
        builds.append(len(documents))
        return original_from_documents(documents, **kwargs)

    monkeypatch.setattr(BM25Retriever, "from_documents", classmethod(counting_from_documents))

    first = await KnowledgeBaseManager.search_industry("灌溉", team_id=3, db=db, top_k=3)
    assert builds == [3]
    assert any("灌溉" in result.content for result in first)

    await db.delete(old_docs[2])
    await db.flush()
    new_doc = IndustryKnowledge(team_id=3, source_file="doc.txt", content="新分块：紫薇病虫害防治。")
    db.add(new_doc)
    await db.flush()
    assert new_doc.id == 3  # 前提成立：文档数与最大 ID 回到旧签名

    second = await KnowledgeBaseManager.search_industry("紫薇", team_id=3, db=db, top_k=3)
    assert builds == [3, 3]  # 内容指纹变化触发重建
    assert any("紫薇" in result.content for result in second)


async def test_search_industry_reads_weights_and_top_k_from_settings(db, monkeypatch):
    """未显式传参时，混合权重与返回条数读取 settings，配置项不再失效。"""
    from app.core.config import settings
    from app.services import knowledge_base

    db.add_all([
        IndustryKnowledge(team_id=5, source_file="doc.txt", content=f"灌溉条目{i}")
        for i in range(6)
    ])
    await db.flush()
    knowledge_base._BM25_CACHE.clear()

    captured: dict = {}

    class FakeChroma:
        def as_retriever(self, search_kwargs=None):
            return "vector-retriever"

    class FakeEnsemble:
        def __init__(self, retrievers, weights):
            captured["weights"] = weights

        async def ainvoke(self, _query):
            from langchain_core.documents import Document

            return [Document(page_content=f"灌溉条目{i}") for i in range(6)]

    monkeypatch.setattr(knowledge_base, "_get_chroma", lambda _collection: FakeChroma())
    monkeypatch.setattr("langchain.retrievers.EnsembleRetriever", FakeEnsemble)
    monkeypatch.setattr(settings, "BM25_WEIGHT", 0.7)
    monkeypatch.setattr(settings, "VECTOR_WEIGHT", 0.3)
    monkeypatch.setattr(settings, "RAG_TOP_K", 4)

    results = await KnowledgeBaseManager.search_industry("灌溉", team_id=5, db=db)

    assert captured["weights"] == [0.7, 0.3]
    assert len(results) == 4


async def test_exact_pdf_phrase_match_is_ranked_before_semantic_neighbor(db, monkeypatch):
    """显式开启精确匹配（prepend）时，PDF 兼容字符标题命中块应置顶。

    生产默认已关闭精确匹配（调参记录1.2：rerank 后增益仅 0.3pp）；本测试
    保障该降级兜底选项仍可用。
    """
    db.add_all([
        IndustryKnowledge(
            team_id=3,
            source_file="3/knowledge/园林施工.pdf",
            content="硬景通病包括铺装空鼓开裂和园路积水。",
        ),
        IndustryKnowledge(
            team_id=3,
            source_file="3/knowledge/园林施工.pdf",
            content="前置正文。" * 100 + "2.2.1园路与铺装⼯程：园路分为主园路、次园路、游步道。",
        ),
        IndustryKnowledge(
            team_id=3,
            source_file="3/knowledge/园林施工.pdf",
            content="块。\n2.2.1园路与铺装⼯程：园路分为主园路、次园路、游步道。",
        ),
    ])
    await db.flush()

    def fail_vector_search(_collection: str):
        raise RuntimeError("test uses BM25 fallback")

    monkeypatch.setattr("app.services.knowledge_base._get_chroma", fail_vector_search)
    results = await KnowledgeBaseManager.search_industry(
        "园路与铺装⼯程", team_id=3, db=db, top_k=2, exact_strategy="prepend"
    )

    assert results
    assert results[0].content.startswith("块。")
    assert "园路与铺装⼯程" in results[0].content
    assert results[0].source_file == "园林施工.pdf"
