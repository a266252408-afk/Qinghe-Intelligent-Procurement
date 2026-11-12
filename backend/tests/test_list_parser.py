"""采购清单解析兜底逻辑测试。"""
from app.agents.list_parser import _fallback_parse


def test_fallback_parse_csv_table():
    raw = "品种,规格,数量,单位,单价\n香樟,胸径12cm,8,株,860\n桂花,地径8cm,10,株,520\n"
    result = _fallback_parse(raw)
    assert result.confidence == 0.85
    assert len(result.items) == 2
    assert result.items[0].species == "香樟"
    assert result.items[0].quantity == 8
    assert result.items[0].unit_price == 860


def test_fallback_parse_tab_table_and_skips_total():
    raw = "序号\t品种\t规格\t数量\t单位\n1\t银杏\t胸径15cm\t12\t株\n合计\t\t\t12\t株\n"
    result = _fallback_parse(raw)
    assert len(result.items) == 1
    assert result.items[0].species == "银杏"
