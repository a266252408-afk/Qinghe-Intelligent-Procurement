# SDD — 比价结果缓存（compare_cache）

> **代码位置**：`backend/app/services/compare_cache.py`
> **定位**：进程内 TTL + LRU 缓存，避免重复触发重量档比价建议。

---

## 1. 功能描述

同一团队、同一采购单，在报价集合与比价权重未变化时，重复点击"对比报价"直接复用上次结果，
跳过重量档大模型建议生成，降低费用与等待时间。

缓存使用 `OrderedDict` 实现，不引入外部依赖。报价新增/删除会改变报价集合指纹，
自然产生新键；旧条目按 TTL 过期或超出容量后被 LRU 淘汰。

> 缓存为**进程内存**：多 worker 部署时每个 worker 各自持有独立缓存，命中率按 worker 分摊。
> 数据变更（报价/权重）由键指纹隔离，无需主动失效。

---

## 2. 接口签名

```python
TTL_SECONDS = 30 * 60      # 缓存有效期（秒）
MAX_ENTRIES = 128          # 最大缓存条数

def build_key(
    team_id: int,
    order_id: int,
    quote_ids: list[int],                          # 报价集合指纹
    weights: tuple[float, float, float, float],    # 价格/历史/交期/付款权重
) -> tuple: ...

def get(key: tuple) -> dict | None:
    """命中返回结果并刷新 LRU 顺序；未命中或过期返回 None。"""

def set(key: tuple, payload: dict) -> None:
    """写入缓存；超出 MAX_ENTRIES 时淘汰最久未使用条目。"""

def clear() -> None:
    """清空缓存（测试与运维用）。"""
```

调用方负责生成稳定的 `quote_ids` 列表；本模块内部会对报价 ID 排序后再入键，
避免同一集合因顺序不同产生多个缓存条目。

---

## 3. 外部依赖

仅依赖标准库 `time`、`collections`，无数据库、无大模型、无第三方库。

---

## 4. 异常处理

- 缓存未命中或已过期：返回 `None`，调用方正常重新计算。
- 进程重启：缓存自然清空，不影响正确性。
- 本模块不吞异常；传入不可哈希的键会在 `get/set` 时抛出 `TypeError`，
  由调用方保证键类型稳定。
- 缓存命中不保证数据绝对新鲜，适用于"报价未变化时重复查看"的场景；
  报价或权重的任何变化都会生成新键。
