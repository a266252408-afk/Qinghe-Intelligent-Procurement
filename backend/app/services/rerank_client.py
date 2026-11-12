"""重排序客户端 — 调 Cohere 风格 /rerank 接口（SiliconFlow bge-reranker-v2-m3）

职责：对混合召回的候选文档按"查询-文档"语义相关度重排。
设计约束：
- 实例由 LLMFactory.get_rerank_client() 缓存提供（大模型调用统一走工厂）；
- 经 LLMGate rerank 档做并发/超时闸门；调用后记 LLMCallLogger（写失败不阻断）；
- 任何异常只 warning 并返回空列表，调用方保持原排序（优雅降级，不破坏主链路）。
"""
import logging
import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class RerankClient:
    """Cohere 风格 rerank API 客户端（无状态，实例缓存由 LLMFactory 负责）"""

    def __init__(self, model: str, base_url: str, api_key: str, timeout_s: float = 30.0):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    async def rerank(self, query: str, documents: list[str], top_n: int | None = None,
                     *, agent_name: str = "knowledge_rerank", session=None) -> list[tuple[int, float]]:
        """返回 [(文档下标, 相关度分)] 按分数降序；失败/未配置返回 []。

        session 传入 AsyncSession 时记录 LLMCallLogger 调用日志（成本可观测）。
        """
        if not documents or not self.api_key:
            return []
        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "return_documents": False,
        }
        if top_n is not None:
            payload["top_n"] = top_n
        start = time.perf_counter()
        try:
            from app.services.llm_gate import LLMGate

            async with LLMGate.acquire("rerank"):
                body = await self._post_with_retry(payload=payload)
        except Exception as exc:  # noqa: BLE001 — 降级为主链路保命，任何失败都不上抛
            logger.warning("rerank 调用失败，退回混排原序：%s", exc)
            return []

        latency_ms = int((time.perf_counter() - start) * 1000)
        results = [
            (item["index"], float(item["relevance_score"]))
            for item in body.get("results", [])
            if 0 <= item.get("index", -1) < len(documents)
        ]
        results.sort(key=lambda pair: pair[1], reverse=True)
        await self._log_usage(agent_name, body, latency_ms, session)
        return results

    async def _post_with_retry(self, payload: dict) -> dict:
        """POST /rerank，429 按服务端 Retry-After（缺省指数退避）重试至多 3 次。"""
        import asyncio

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                    resp = await client.post(
                        f"{self.base_url}/rerank",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                    )
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 429 or attempt == 2:
                    raise
                retry_after = exc.response.headers.get("Retry-After")
                delay = float(retry_after) if (retry_after or "").isdigit() else 2.0 * (attempt + 1)
                logger.warning("rerank 429 限速，%.1fs 后重试（第 %d 次）", delay, attempt + 1)
                last_exc = exc
                await asyncio.sleep(delay)
        raise last_exc  # pragma: no cover — 循环必经 raise/return

    @staticmethod
    async def _log_usage(agent_name: str, body: dict, latency_ms: int, session) -> None:
        """记录 rerank 调用日志；响应无计费字段时 tokens 记 0。"""
        if session is None:
            return
        try:
            from app.services.llm_logger import LLMCallLogger

            usage = body.get("usage") or body.get("meta", {}).get("billed_units") or {}
            await LLMCallLogger.log(
                agent_name=agent_name,
                model=settings.RERANK_MODEL,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
                cost=0.0,
                latency_ms=latency_ms,
                cache_hit=False,
                session_id="",
                db=session,
            )
        except Exception as exc:  # noqa: BLE001 — 日志失败不影响主链路
            logger.warning("rerank 调用日志写入失败：%s", exc)
