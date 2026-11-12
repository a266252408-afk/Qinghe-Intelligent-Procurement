"""LLM 并发闸门 — 按档位限制进程内在途请求数，防止突发流量打爆模型供应商
依据：docs/module-sdd/llm_factory.md（档位划分），施工日志 2026-08-27 并发加固
"""
import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import ClassVar, TypeVar

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 档位 → 配置项名前缀映射（与 config.Settings 字段对应）
_TIERS: dict[str, tuple[str, str]] = {
    "light": ("LLM_LIGHT_CONCURRENCY", "LLM_LIGHT_TIMEOUT_S"),
    "medium": ("LLM_MEDIUM_CONCURRENCY", "LLM_MEDIUM_TIMEOUT_S"),
    "heavy": ("LLM_HEAVY_CONCURRENCY", "LLM_HEAVY_TIMEOUT_S"),
    "embedding": ("EMBEDDING_CONCURRENCY", "EMBEDDING_TIMEOUT_S"),
    "rerank": ("RERANK_CONCURRENCY", "RERANK_TIMEOUT_S"),
    "jev": ("JEV_CONCURRENCY", "JEV_TIMEOUT_S"),
}


class LLMGate:
    """按档位的并发闸门：信号量排队 + 非流式超时 + 网络类瞬时错误有限重试"""

    _sems: ClassVar[dict[str, asyncio.Semaphore]] = {}
    # 延迟解析的重试异常类型集合（openai 包经 langchain-openai 间接安装）
    _retry_errors: ClassVar[tuple[type[Exception], ...] | None] = None

    @classmethod
    def _semaphore(cls, tier: str) -> asyncio.Semaphore:
        """获取档位信号量，首次使用时按配置创建并缓存"""
        if tier not in _TIERS:
            tier = "medium"  # 未知档位按中量档兜底，避免调用方崩溃
        conc_cfg, _ = _TIERS[tier]
        if tier not in cls._sems:
            limit = max(getattr(settings, conc_cfg), 0)
            if limit == 0:  # 0 表示不限制：用足够大的信号量保持同一实现路径
                limit = 10_000
            cls._sems[tier] = asyncio.Semaphore(limit)
            logger.info("LLM 并发闸门启用：%s 在途上限=%d", tier, limit)
        return cls._sems[tier]

    @classmethod
    def timeout_s(cls, tier: str) -> float:
        """档位对应的单次非流式调用超时秒数"""
        if tier not in _TIERS:
            tier = "medium"
        _, timeout_cfg = _TIERS[tier]
        return float(getattr(settings, timeout_cfg))

    @classmethod
    def _network_error_types(cls) -> tuple[type[Exception], ...]:
        """可重试的网络类瞬时错误（连接失败/超时/限流）"""
        if cls._retry_errors is None:
            types: list[type[Exception]] = [asyncio.TimeoutError, ConnectionError]
            try:
                from openai import APIConnectionError, APITimeoutError, RateLimitError
                types += [APIConnectionError, APITimeoutError, RateLimitError]
            except ImportError:
                logger.debug("openai 包不可用，仅按内置异常类型重试")
            cls._retry_errors = tuple(types)
        return cls._retry_errors

    @classmethod
    @asynccontextmanager
    async def acquire(cls, tier: str) -> AsyncIterator[None]:
        """流式调用使用：只做并发排队，不设总超时（不适用于重试）"""
        sem = cls._semaphore(tier)
        started_at = time.monotonic()
        queued = sem.locked()  # 上限已被占满时说明需要排队
        async with sem:
            if queued:
                logger.debug("LLG[%s] 排队等待 %.0fms", tier, (time.monotonic() - started_at) * 1000)
            yield

    @classmethod
    async def run(
        cls,
        tier: str,
        op: Callable[[], Awaitable[T]],
        *,
        attempts: int | None = None,
    ) -> T:
        """非流式调用使用：信号量内执行 op()，带超时与网络类错误的有限重试。

        op 是零参异步工厂函数；每次重试都会重新调用它以重建请求。
        """
        if attempts is None:
            attempts = max(int(settings.LLM_RETRY_ATTEMPTS), 1)
        backoff = float(settings.LLM_RETRY_BACKOFF_S)
        timeout = cls.timeout_s(tier)
        sem = cls._semaphore(tier)

        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            async with sem:
                try:
                    return await asyncio.wait_for(op(), timeout=timeout)
                except cls._network_error_types() as exc:
                    last_exc = exc
                    if attempt >= attempts:
                        break
                    logger.warning(
                        "LLMGate[%s] 第 %d 次调用瞬时失败将重试：%s",
                        tier, attempt, exc,
                    )
            await asyncio.sleep(backoff * (2 ** (attempt - 1)))
        assert last_exc is not None
        raise last_exc
