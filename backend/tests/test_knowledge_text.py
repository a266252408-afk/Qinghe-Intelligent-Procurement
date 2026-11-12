"""行业知识文档清洗与递归分块测试。"""

from app.services.knowledge_base import clean_knowledge_text, split_knowledge_text


def test_clean_knowledge_text_removes_common_noise() -> None:
    """清洗控制字符、空行和常见分隔线。"""
    content = "标题\r\n\r\n---\r\n规格\u0000：12cm   数量：10"
    assert clean_knowledge_text(content) == "标题\n规格：12cm 数量：10"


def test_split_knowledge_text_uses_recursive_chunks() -> None:
    """长文本应切分为不超过配置上限的分块。"""
    chunks = split_knowledge_text("园林苗木采购规范。" * 200)
    assert len(chunks) > 1
    assert all(len(chunk) <= 1000 for chunk in chunks)
