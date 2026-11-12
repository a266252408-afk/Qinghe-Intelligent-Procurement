"""比价 Agent 确定性评分逻辑测试（无需调用 LLM）"""
import pytest

from app.services.compare_scoring import (
    build_material_price_comparisons,
    build_supplier_quote_totals,
    calc_scores,
    normalize_inv,
    payment_to_score,
)
from app.schemas.compare import CompareWeights


def _make_weights():
    return CompareWeights(price=0.4, history=0.3, delivery=0.2, payment=0.1)


def test_normalize_inv_lower_is_better():
    assert normalize_inv(10, 10, 20) == 1.0   # 最低价，得满分
    assert normalize_inv(20, 10, 20) == 0.0   # 最高价，得零分
    assert normalize_inv(15, 10, 20) == 0.5   # 中间价，得中分


def test_normalize_inv_equal_bounds():
    assert normalize_inv(10, 10, 10) == 0.5   # 上下界相等，返回 0.5


def test_payment_to_score():
    assert payment_to_score("月结30天") == 1.0
    assert payment_to_score("货到付款") == 0.7
    assert payment_to_score("现款现货") == 0.3
    assert payment_to_score(None) == 0.5
    assert payment_to_score("其他条件") == 0.5


def test_calc_scores_sorted_by_total():
    """两家供应商，价格低的排前面（在其他条件相同时）"""
    from unittest.mock import MagicMock

    def _make_quote(supplier, price, delivery):
        item = MagicMock()
        item.unit_price = price
        item.delivery_days = delivery
        item.payment_terms = "月结"
        q = MagicMock()
        q.supplier_name = supplier
        q.id = 1
        q.items = [item]
        return q

    quotes = [_make_quote("A", 100.0, 10), _make_quote("B", 200.0, 10)]
    scores = calc_scores(quotes, _make_weights())

    assert scores[0].supplier_name == "A"   # A 价格低，排第一
    assert scores[0].total_score > scores[1].total_score


def test_calc_scores_empty_quotes():
    assert calc_scores([], _make_weights()) == []


def test_material_price_comparison_groups_same_material_and_spec():
    """相同材料规格按供应商横向返回单价。"""
    from unittest.mock import MagicMock

    def quote(supplier, price):
        item = MagicMock(spec=["species", "spec", "unit", "unit_price", "total_price", "quantity"])
        item.species, item.spec, item.unit = "香樟", "胸径12cm", "株"
        item.unit_price, item.total_price, item.quantity = price, None, 10
        result = MagicMock()
        result.supplier_name, result.id, result.items = supplier, 1, [item]
        return result

    comparisons = build_material_price_comparisons([quote("甲供应商", 100), quote("乙供应商", 120)])
    assert len(comparisons) == 1
    prices = {item.supplier_name: item.unit_price for item in comparisons[0].suppliers}
    assert prices == {"甲供应商": 100.0, "乙供应商": 120.0}


def test_material_price_comparison_normalizes_formatting_variants():
    """材料、规格和单位仅有空白或全角尺寸符号差异时应合并。"""
    from unittest.mock import MagicMock

    def quote(supplier, species, spec, unit, price):
        item = MagicMock(spec=["species", "spec", "unit", "unit_price"])
        item.species, item.spec, item.unit = species, spec, unit
        item.unit_price = price
        result = MagicMock()
        result.supplier_name, result.id, result.items = supplier, 1, [item]
        return result

    comparisons = build_material_price_comparisons([
        quote("甲供应商", " 景观防腐木 ", "150 × 50 mm", " m ", 100),
        quote("乙供应商", "景观 防腐木", "150x50mm", "m", 120),
    ])

    assert len(comparisons) == 1
    assert comparisons[0].species == "景观防腐木"
    assert comparisons[0].spec == "150 × 50 mm"


def test_supplier_quote_totals_use_line_total_or_fallback():
    """供应商总额优先使用行总价，缺失时补算数量乘单价。"""
    from unittest.mock import MagicMock

    first = MagicMock(spec=["total_price", "quantity", "unit_price"])
    first.total_price, first.quantity, first.unit_price = 500, 10, 80
    second = MagicMock(spec=["total_price", "quantity", "unit_price"])
    second.total_price, second.quantity, second.unit_price = None, 5, 60
    quote = MagicMock(spec=["supplier_name", "id", "items"])
    quote.supplier_name, quote.id, quote.items = "甲供应商", 1, [first, second]

    totals = build_supplier_quote_totals([quote])
    assert totals[0].total_price == 800.0


def test_weights_sum_must_equal_one():
    from pydantic import ValidationError
    with pytest.raises(Exception):  # WeightSumError 或 ValidationError
        CompareWeights(price=0.5, history=0.5, delivery=0.5, payment=0.5)
