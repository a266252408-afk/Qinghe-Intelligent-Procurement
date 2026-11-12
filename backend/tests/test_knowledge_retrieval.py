"""行业知识库精确短语优先检索测试。"""
import pytest

from app.models.knowledge import IndustryKnowledge
from app.services.knowledge_base import KnowledgeBaseManager, _source_file_name

pytestmark = pytest.mark.asyncio


async def test_old_generated_storage_name_has_explicit_fallback_label():
    """历史数据没有原始文件名时，不向用户展示 UUID。"""
    assert _source_file_name("3/knowledge/2026/08/" + "a" * 32 + ".pdf") == "历史上传文档（原始文件名未记录）"


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
