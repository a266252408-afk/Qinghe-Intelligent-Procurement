"""LLM 调用日志服务 — 记录每次大模型调用的成本与性能数据
依据：docs/module-sdd/llm_logger_service.md
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_log import LLMCallLog
from app.schemas.llm_logger import LLMCallLogCreate, LLMCallSummary

logger = logging.getLogger(__name__)


class LLMCallLogger:
    """LLM 调用成本可观测服务（开发者侧，写入失败不阻断主链路）"""

    @staticmethod
    async def log(
        agent_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        latency_ms: int,
        cache_hit: bool,
        session_id: str,
        db: AsyncSession,
    ) -> None:
        """写入 llm_call_logs；任何 DB 异常只记录 warning，不向上抛出

        使用 SAVEPOINT（begin_nested）写入：失败时仅回滚到保存点，
        会话保持可用，且不会丢弃同一事务中先于日志的其他业务写入。
        """
        try:
            async with db.begin_nested():
                record = LLMCallLog(
                    agent_name=agent_name,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=cost,
                    latency_ms=latency_ms,
                    cache_hit=cache_hit,
                    session_id=session_id,
                )
                db.add(record)
                await db.flush()
        except Exception as exc:
            logger.warning("LLMCallLogger.log 写入失败: %s", exc)

    @staticmethod
    async def summary_by_model(days: int, db: AsyncSession) -> list[LLMCallSummary]:
        """按模型汇总最近 N 天的调用数据"""
        try:
            since = datetime.now(timezone.utc) - timedelta(days=days)
            stmt = (
                select(
                    LLMCallLog.model.label("key"),
                    func.count(LLMCallLog.id).label("total_calls"),
                    func.sum(LLMCallLog.cost).label("total_cost"),
                    func.avg(LLMCallLog.latency_ms).label("avg_latency_ms"),
                )
                .where(LLMCallLog.created_at >= since)
                .group_by(LLMCallLog.model)
            )
            rows = (await db.execute(stmt)).all()
            return [
                LLMCallSummary(
                    key=r.key,
                    total_calls=r.total_calls,
                    total_cost=float(r.total_cost or 0),
                    avg_latency_ms=float(r.avg_latency_ms or 0),
                )
                for r in rows
            ]
        except Exception as exc:
            logger.warning("LLMCallLogger.summary_by_model 查询失败: %s", exc)
            return []

    @staticmethod
    async def summary_by_agent(days: int, db: AsyncSession) -> list[LLMCallSummary]:
        """按 Agent 汇总最近 N 天的调用数据"""
        try:
            since = datetime.now(timezone.utc) - timedelta(days=days)
            stmt = (
                select(
                    LLMCallLog.agent_name.label("key"),
                    func.count(LLMCallLog.id).label("total_calls"),
                    func.sum(LLMCallLog.cost).label("total_cost"),
                    func.avg(LLMCallLog.latency_ms).label("avg_latency_ms"),
                )
                .where(LLMCallLog.created_at >= since)
                .group_by(LLMCallLog.agent_name)
            )
            rows = (await db.execute(stmt)).all()
            return [
                LLMCallSummary(
                    key=r.key,
                    total_calls=r.total_calls,
                    total_cost=float(r.total_cost or 0),
                    avg_latency_ms=float(r.avg_latency_ms or 0),
                )
                for r in rows
            ]
        except Exception as exc:
            logger.warning("LLMCallLogger.summary_by_agent 查询失败: %s", exc)
            return []
