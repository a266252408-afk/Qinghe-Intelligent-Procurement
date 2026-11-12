"""比价评分纯函数模块（无 LLM 依赖，供测试和 CompareAgent 共用）"""
from collections import defaultdict
from typing import TYPE_CHECKING
import re
import unicodedata

from app.schemas.compare import (
    CompareWeights,
    MaterialPriceComparison,
    MaterialSupplierPrice,
    SupplierQuoteTotal,
    SupplierScore,
)

if TYPE_CHECKING:
    from app.models.quote import Quote


def calc_scores(quotes: list, weights: CompareWeights) -> list[SupplierScore]:
    """多维度评分：价格（越低越好）/ 历史评级 / 交期（越短越好）/ 付款条件"""
    supplier_prices: dict[str, list[float]] = defaultdict(list)
    supplier_meta: dict[str, dict] = {}

    for q in quotes:
        name = q.supplier_name or f"supplier_{q.id}"
        for item in q.items:
            if item.unit_price is not None:
                supplier_prices[name].append(float(item.unit_price))
        if name not in supplier_meta:
            first_item = q.items[0] if q.items else None
            supplier_meta[name] = {
                "unit_price": float(q.items[0].unit_price) if q.items and q.items[0].unit_price else None,
                "delivery_days": first_item.delivery_days if first_item else None,
                "payment_terms": first_item.payment_terms if first_item else None,
            }

    if not supplier_prices:
        return []

    avg_prices = {k: sum(v) / len(v) for k, v in supplier_prices.items()}
    min_p, max_p = min(avg_prices.values()), max(avg_prices.values())

    all_delivery = [m["delivery_days"] for m in supplier_meta.values() if m["delivery_days"] is not None]
    min_d = min(all_delivery) if all_delivery else None
    max_d = max(all_delivery) if all_delivery else None

    scores: list[SupplierScore] = []
    for name, avg_p in avg_prices.items():
        meta = supplier_meta[name]
        price_score = normalize_inv(avg_p, min_p, max_p)
        delivery_score = (
            normalize_inv(meta["delivery_days"], min_d, max_d)
            if meta["delivery_days"] is not None and min_d is not None
            else 0.5
        )
        payment_score = payment_to_score(meta["payment_terms"])
        history_score = 0.5  # 无历史评级时默认中等

        total = (
            weights.price * price_score
            + weights.history * history_score
            + weights.delivery * delivery_score
            + weights.payment * payment_score
        )
        scores.append(SupplierScore(
            supplier_name=name,
            price_score=round(price_score, 4),
            history_score=round(history_score, 4),
            delivery_score=round(delivery_score, 4),
            payment_score=round(payment_score, 4),
            total_score=round(total, 4),
            unit_price=meta["unit_price"],
            delivery_days=meta["delivery_days"],
            payment_terms=meta["payment_terms"],
        ))

    return sorted(scores, key=lambda s: s.total_score, reverse=True)


def build_material_price_comparisons(quotes: list) -> list[MaterialPriceComparison]:
    """按材料、规格和单位汇总各供应商报价单价。"""
    grouped: dict[tuple[str, str, str], dict[str, list[float]]] = defaultdict(dict)
    display_values: dict[tuple[str, str, str], tuple[str, str, str]] = {}
    for quote in quotes:
        supplier = quote.supplier_name or f"supplier_{quote.id}"
        for item in quote.items:
            if item.unit_price is None:
                continue
            values = tuple(_display_value(value) for value in (item.species, item.spec, item.unit))
            key = tuple(_comparison_key(value) for value in values)
            supplier_prices = grouped.setdefault(key, {})
            supplier_prices.setdefault(supplier, []).append(float(item.unit_price))
            display_values.setdefault(key, values)

    comparisons: list[MaterialPriceComparison] = []
    for key, supplier_prices in sorted(grouped.items()):
        species, spec, unit = display_values[key]
        suppliers = [
            MaterialSupplierPrice(
                supplier_name=name,
                unit_price=round(sum(prices) / len(prices), 2),
            )
            for name, prices in sorted(supplier_prices.items())
        ]
        comparisons.append(
            MaterialPriceComparison(species=species, spec=spec, unit=unit, suppliers=suppliers)
        )
    return comparisons


def _display_value(value: str | None) -> str:
    """统一展示值，保留单词之间的一个空格。"""
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", normalized).strip()


def _comparison_key(value: str) -> str:
    """生成材料对比键，消除全角字符、空白和常见尺寸分隔符差异。"""
    normalized = value.casefold().replace("×", "x").replace("＊", "x").replace("*", "x")
    return re.sub(r"\s+", "", normalized)


def build_supplier_quote_totals(quotes: list) -> list[SupplierQuoteTotal]:
    """汇总供应商报价总额，缺少行总价时用数量乘单价补算。"""
    totals: dict[str, float] = defaultdict(float)
    for quote in quotes:
        supplier = quote.supplier_name or f"supplier_{quote.id}"
        totals[supplier] += sum(_item_total(item) for item in quote.items)
    return [
        SupplierQuoteTotal(supplier_name=name, total_price=round(total, 2))
        for name, total in sorted(totals.items())
    ]


def _item_total(item) -> float:
    """读取报价行总价，缺失时按数量和供应商报价补算。"""
    if item.total_price is not None:
        return float(item.total_price)
    if item.quantity is not None and item.unit_price is not None:
        return float(item.quantity) * float(item.unit_price)
    return 0.0


def normalize_inv(val: float, lo: float | None, hi: float | None) -> float:
    """反向归一化：值越小分越高"""
    if lo is None or hi is None or lo == hi:
        return 0.5
    return 1.0 - (val - lo) / (hi - lo)


def payment_to_score(terms: str | None) -> float:
    """付款条件评分：现款=0.3，货到付款=0.7，月结=1.0，其它=0.5"""
    if not terms:
        return 0.5
    t = terms.lower()
    if "现" in t or "预" in t:
        return 0.3
    if "到货" in t or "到付" in t:
        return 0.7
    if "月结" in t or "账期" in t:
        return 1.0
    return 0.5


def bar_chart(scores: list[SupplierScore]) -> dict:
    return {
        "xAxis": {"data": [s.supplier_name for s in scores]},
        "series": [{"name": "综合评分", "type": "bar", "data": [s.total_score for s in scores]}],
    }


def radar_chart(scores: list[SupplierScore], weights: CompareWeights) -> dict:
    indicators = [
        {"name": "价格", "max": 1},
        {"name": "历史", "max": 1},
        {"name": "交期", "max": 1},
        {"name": "付款", "max": 1},
    ]
    series_data = [
        {
            "name": s.supplier_name,
            "value": [s.price_score, s.history_score, s.delivery_score, s.payment_score],
        }
        for s in scores
    ]
    return {"radar": {"indicator": indicators}, "series": [{"type": "radar", "data": series_data}]}
