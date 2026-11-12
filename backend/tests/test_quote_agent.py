"""报价单解析 Agent 测试。"""
from app.agents.quote import parse_quote


def test_parse_quote_supports_supplier_header_and_chinese_price_alias(tmp_path):
    """兼容供应商抬头字段、含税单价和交货期字段。"""
    path = tmp_path / "supplier.csv"
    path.write_text(
        "供应商名称,报价日期,有效期,序号,品种,规格,数量,单位,含税单价(元),总价(元),交货期(天),付款条件\n"
        "示例园林,2026-08-20,2026-09-20,1,香樟,胸径12cm,5,株,860,4300,7,到货付款\n",
        encoding="utf-8",
    )

    items = parse_quote(str(path))

    assert len(items) == 1
    assert items[0].species == "香樟"
    assert items[0].unit_price == 860
    assert items[0].delivery_days == 7
