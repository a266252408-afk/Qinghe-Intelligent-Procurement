"""比价结果缓存测试（无需数据库与 LLM）。"""
import time

from app.schemas.compare import CompareWeights
from app.services import compare_cache


def setup_function(_fn):
    compare_cache.clear()


def teardown_function(_fn):
    compare_cache.clear()


def test_cache_hit_returns_payload():
    key = compare_cache.build_key(1, 10, [3, 1], (0.4, 0.3, 0.2, 0.1))
    compare_cache.set(key, {"ai_suggestion": "推荐A"})
    assert compare_cache.get(key) == {"ai_suggestion": "推荐A"}


def test_cache_miss_on_different_quotes_or_weights():
    """报价集合或权重变化视为新键，不命中旧结果。"""
    key = compare_cache.build_key(1, 10, [3, 1], (0.4, 0.3, 0.2, 0.1))
    compare_cache.set(key, {"v": 1})
    # 新增报价 → 键变化
    assert compare_cache.get(compare_cache.build_key(1, 10, [3, 1, 5], (0.4, 0.3, 0.2, 0.1))) is None
    # 权重变化 → 键变化
    assert compare_cache.get(compare_cache.build_key(1, 10, [1, 3], (0.5, 0.2, 0.2, 0.1))) is None
    # 团队/采购单不同 → 键变化
    assert compare_cache.get(compare_cache.build_key(2, 10, [1, 3], (0.4, 0.3, 0.2, 0.1))) is None
    assert compare_cache.get(compare_cache.build_key(1, 11, [1, 3], (0.4, 0.3, 0.2, 0.1))) is None


def test_cache_expires_after_ttl(monkeypatch):
    key = compare_cache.build_key(1, 10, [1], (0.4, 0.3, 0.2, 0.1))
    compare_cache.set(key, {"v": 1})
    # 直接把写入时间拨回 TTL 之前，模拟过期
    created_at, payload = compare_cache._store[key]
    compare_cache._store[key] = (created_at - compare_cache.TTL_SECONDS - 1, payload)
    assert compare_cache.get(key) is None
    assert key not in compare_cache._store


def test_cache_lru_eviction():
    for index in range(compare_cache.MAX_ENTRIES + 1):
        key = compare_cache.build_key(1, index, [index], (0.4, 0.3, 0.2, 0.1))
        compare_cache.set(key, {"v": index})
    # 超上限后最旧的键被淘汰，总条数不超过上限
    assert len(compare_cache._store) == compare_cache.MAX_ENTRIES
    oldest = compare_cache.build_key(1, 0, [0], (0.4, 0.3, 0.2, 0.1))
    assert compare_cache.get(oldest) is None


def test_weights_tuple_from_schema():
    """CompareWeights 与缓存键元组字段一一对应。"""
    weights = CompareWeights()
    assert (weights.price, weights.history, weights.delivery, weights.payment) == (0.4, 0.3, 0.2, 0.1)
