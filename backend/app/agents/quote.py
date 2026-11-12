"""报价单解析 Agent：将供应商文件转换为可人工确认的结构化报价。"""
import csv
import io
import re
from pathlib import Path

from app.core.exceptions import ParseError
from app.schemas.quote import QuoteItemInput


_ALIASES = {
    "species": {"品种", "品名", "名称", "物料名称"},
    "spec": {"规格", "规格型号", "型号"},
    "quantity": {"数量", "报价数量"},
    "unit": {"单位"},
    "unit_price": {"单价", "报价", "含税单价", "含税单价(元)", "单价(元)", "单价（元）"},
    "total_price": {"总价", "总价(元)", "合计", "含税总价", "含税总价(元)"},
    "delivery_days": {"交货期", "交货期(天)", "交货天数", "供货周期"},
    "payment_terms": {"付款条件", "付款方式"},
    "valid_until": {"报价有效期", "有效期"},
}


def _decode_bytes(data: bytes) -> str:
    """按 utf-8-sig → gbk → utf-8(replace) 顺序解码。

    utf-8-sig 兼容带 BOM 的文件（Windows 记事本/Excel 另存常态）；
    GBK 兜底覆盖国产 Excel 直接另存的中文 CSV；两者都失败时退回原 replace 行为。
    """
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _read_text(file_path: str) -> str:
    """读取报价文件文本，支持 txt、csv 和 xlsx。"""
    path = Path(file_path)
    if not path.exists():
        raise ParseError("报价文件不存在")
    if path.suffix.lower() in {".txt", ".csv"}:
        return _decode_bytes(path.read_bytes())
    if path.suffix.lower() == ".xlsx":
        import openpyxl

        workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        rows = []
        for sheet in workbook.worksheets:
            rows.extend("\t".join(str(cell) for cell in row if cell is not None) for row in sheet.iter_rows(values_only=True))
        return "\n".join(row for row in rows if row)
    raise ParseError("报价单仅支持 xlsx、csv、txt 文件")


def _number(value: str | None) -> float | None:
    """将单元格转换为数字，无法转换时返回空值。"""
    if value is None or not str(value).strip():
        return None
    try:
        return float(str(value).replace(",", "").replace("￥", "").strip())
    except ValueError:
        return None


def _index(header: list[str], names: set[str]) -> int | None:
    normalized = {_normalize(value) for value in names}
    return next((idx for idx, value in enumerate(header) if _normalize(value) in normalized), None)


def _normalize(value: str) -> str:
    return str(value).strip().replace(' ', '').replace('（', '(').replace('）', ')')


def parse_quote(file_path: str) -> list[QuoteItemInput]:
    """解析供应商报价表，返回用户确认前的报价项。"""
    raw = _read_text(file_path)
    # 有 tab 用 tab：xlsx 转出的文本里千分位逗号（3,180.00）不是分隔符
    delimiter = "\t" if "\t" in raw else ","
    rows = list(csv.reader(io.StringIO(raw), delimiter=delimiter))
    if not rows:
        raise ParseError("报价单为空")
    header = [str(value).strip() for value in rows[0]]
    indexes = {key: _index(header, names) for key, names in _ALIASES.items()}
    if indexes["species"] is None or indexes["unit_price"] is None:
        raise ParseError("报价单缺少品种或单价列")
    items = []
    for row in rows[1:]:
        species_idx = indexes["species"]
        price_idx = indexes["unit_price"]
        if species_idx is None or price_idx is None or species_idx >= len(row):
            continue
        species = row[species_idx].strip()
        if not species or species in {"合计", "总计", "小计"}:
            continue
        price = _number(row[price_idx] if price_idx < len(row) else None)
        if price is None:
            continue
        items.append(QuoteItemInput(
            species=species,
            spec=_cell(row, indexes["spec"]),
            unit=_cell(row, indexes["unit"]),
            quantity=_number(_cell(row, indexes["quantity"])),
            unit_price=price,
            total_price=_number(_cell(row, indexes["total_price"])),
            delivery_days=int(_number(_cell(row, indexes["delivery_days"])) or 0) or None,
            payment_terms=_cell(row, indexes["payment_terms"]) or None,
            valid_until=_date(_cell(row, indexes["valid_until"])),
        ))
    if not items:
        raise ParseError("未识别到有效报价项目")
    return items


def _cell(row: list[str], index: int | None) -> str:
    return row[index].strip() if index is not None and index < len(row) else ""


def _date(value: str) -> str | None:
    """规范化日期（斜杠/点 → 连字符，月/日补零），否则 Pydantic 无法解析为 date。"""
    if not value:
        return None
    normalized = re.sub(r"[/.]", "-", value)
    parts = normalized.split("-")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        return "-".join(p.zfill(4 if i == 0 else 2) for i, p in enumerate(parts))
    return normalized
