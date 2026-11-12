"""比价 Agent：多维度评分 + AI 采购建议
依据：docs/module-sdd/compare_agent.md
"""
import time
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NoQuoteError
from app.schemas.compare import CompareInput, CompareResult, CompareWeights, SupplierScore
from app.services import compare_cache
from app.services.llm_logger import LLMCallLogger
from app.services.order_service import PurchaseOrderService
from app.services.compare_scoring import (
    calc_scores as _calc_scores,
    normalize_inv as _normalize_inv,
    payment_to_score as _payment_to_score,
    bar_chart as _bar_chart,
    radar_chart as _radar_chart,
    build_material_price_comparisons as _build_material_price_comparisons,
    build_supplier_quote_totals as _build_supplier_quote_totals,
)

logger = logging.getLogger(__name__)

_SUGGESTION_PROMPT = """\
你是园林工程采购顾问，根据以下比价评分给出简洁的采购建议（150字内）。

采购单ID：{order_id}
评分结果：{scores_text}
权重：价格{price_w} 历史{history_w} 交期{delivery_w} 付款{payment_w}

建议内容需点明推荐供应商并说明原因，注意风险提示。"""


class CompareAgent:
    """比价 Agent：确定性多维度评分 + 重量档 LLM 生成建议"""

    async def compare(
        self,
        data: CompareInput,
        team_id: int,
        session_id: str,
        db: AsyncSession,
    ) -> CompareResult:
        """执行比价，返回评分明细 + ECharts 图表数据 + AI 建议"""
        weights = data.weights or _default_weights()

        # 加载采购单与报价（数据访问归 order_service，Agent 只做编排）
        order = await PurchaseOrderService.get_order_scoped(data.order_id, team_id, db)
        quotes = await PurchaseOrderService.list_quotes_for_order(data.order_id, team_id, db)
        if not quotes:
            raise NoQuoteError()

        # 报价集合与权重未变化时直接复用上次结果，避免重复调用重量档 LLM
        weights_tuple = (
            weights.price, weights.history, weights.delivery, weights.payment,
        )
        cache_key = compare_cache.build_key(
            team_id, data.order_id, [quote.id for quote in quotes], weights_tuple
        )
        cached = compare_cache.get(cache_key)
        if cached is not None:
            await LLMCallLogger.log(
                agent_name="CompareAgent",
                model="cache",
                input_tokens=0,
                output_tokens=0,
                cost=0.0,
                latency_ms=0,
                cache_hit=True,
                session_id=session_id,
                db=db,
            )
            return CompareResult(**cached)

        scores = _calc_scores(quotes, weights)
        material_prices = _build_material_price_comparisons(quotes)
        supplier_totals = _build_supplier_quote_totals(quotes)

        ai_suggestion, ai_source = await self._gen_suggestion(
            data.order_id, scores, weights, session_id, db
        )

        result = CompareResult(
            order_id=data.order_id,
            suppliers=scores,
            bar_chart_option=_bar_chart(scores),
            radar_chart_option=_radar_chart(scores, weights),
            ai_suggestion=ai_suggestion,
            ai_suggestion_source=ai_source,
            weights_used=weights,
            material_price_comparisons=material_prices,
            supplier_quote_totals=supplier_totals,
        )
        compare_cache.set(cache_key, result.model_dump())
        return result

    async def _gen_suggestion(
        self,
        order_id: int,
        scores: list[SupplierScore],
        weights: CompareWeights,
        session_id: str,
        db: AsyncSession,
    ) -> tuple[str, str]:
        """调用重量档 LLM 生成采购建议；失败时降级为模板文本"""
        from langchain.prompts import ChatPromptTemplate
        from app.services.llm_factory import LLMFactory
        from app.services.llm_logger import LLMCallLogger
        scores_text = "\n".join(
            f"  {s.supplier_name}: 总分={s.total_score:.2f}, 价格={s.price_score:.2f}, "
            f"历史={s.history_score:.2f}, 交期={s.delivery_score:.2f}, 付款={s.payment_score:.2f}"
            for s in scores
        )
        prompt = ChatPromptTemplate.from_messages([
            ("human", _SUGGESTION_PROMPT),
        ])
        llm = LLMFactory.get_heavy()
        t0 = time.monotonic()
        try:
            from app.services.llm_gate import LLMGate
            chain = prompt | llm
            resp = await LLMGate.run("heavy", lambda: chain.ainvoke({
                "order_id": order_id,
                "scores_text": scores_text,
                "price_w": weights.price,
                "history_w": weights.history,
                "delivery_w": weights.delivery,
                "payment_w": weights.payment,
            }))
            suggestion = resp.content if hasattr(resp, "content") else str(resp)
            source = "ai"
        except Exception as exc:
            logger.warning("CompareAgent LLM 失败，使用模板建议：%s", exc)
            best = max(scores, key=lambda s: s.total_score) if scores else None
            suggestion = (
                f"综合评分最高供应商为【{best.supplier_name}】（{best.total_score:.2f}分）。"
                if best else "暂无有效报价，建议重新询价。"
            )
            source = "template"

        latency_ms = int((time.monotonic() - t0) * 1000)
        await LLMCallLogger.log(
            agent_name="CompareAgent",
            model=getattr(llm, "model_name", "unknown"),
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            latency_ms=latency_ms,
            cache_hit=False,
            session_id=session_id,
            db=db,
        )
        return suggestion, source


def _default_weights() -> CompareWeights:
    return CompareWeights(
        price=settings.COMPARE_WEIGHT_PRICE,
        history=settings.COMPARE_WEIGHT_HISTORY,
        delivery=settings.COMPARE_WEIGHT_DELIVERY,
        payment=settings.COMPARE_WEIGHT_PAYMENT,
    )
