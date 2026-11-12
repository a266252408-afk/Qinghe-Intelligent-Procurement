"""比价结果进程内缓存。

同一团队同一采购单，报价集合与权重未变化时重复点击"对比报价"直接复用
上次结果，省去重量档 LLM 建议生成，降低成本与等待时间。缓存为进程内存
（OrderedDict + TTL + LRU 上限），无需引入外部依赖；报价新增/删除会改变
报价集合指纹，自然产生新键，旧条目到期后由 LRU/TTL 淘汰。
"""
import time
from collections import OrderedDict

# 缓存有效期（秒）：超过后即使报价未变也重新生成建议
TTL_SECONDS = 30 * 60
# 最大缓存条数：超出后淘汰最久未命中的条目
MAX_ENTRIES = 128

_store: OrderedDict[tuple, tuple[float, dict]] = OrderedDict()


def build_key(
    team_id: int,
    order_id: int,
    quote_ids: list[int],
    weights: tuple[float, float, float, float],
) -> tuple:
    """构造缓存键：团队 + 采购单 + 报价集合指纹 + 权重。"""
    return (team_id, order_id, tuple(sorted(quote_ids)), weights)


def get(key: tuple) -> dict | None:
    """命中返回结果副本并刷新 LRU 顺序，未命中或过期返回 None。"""
    entry = _store.get(key)
    if entry is None:
        return None
    created_at, payload = entry
    if time.monotonic() - created_at > TTL_SECONDS:
        _store.pop(key, None)
        return None
    _store.move_to_end(key)
    return payload


def set(key: tuple, payload: dict) -> None:
    """写入缓存，超上限时淘汰最久未使用条目。"""
    _store[key] = (time.monotonic(), payload)
    _store.move_to_end(key)
    while len(_store) > MAX_ENTRIES:
        _store.popitem(last=False)


def clear() -> None:
    """清空缓存（测试与运维用）。"""
    _store.clear()
