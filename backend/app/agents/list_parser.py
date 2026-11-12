"""清单解析 Agent：从文件或文本中提取结构化采购清单
依据：docs/module-sdd/list_parser_agent.md
"""
import asyncio
import time
import logging
import csv
import io
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ParseError
from app.schemas.list_parser import ParseInput, ParseResult, PurchaseList

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是园林工程采购清单解析器，从文本中提取结构化采购数据。
规则：
1. 每行/每条记录提取：品种名称、规格、数量、单位
2. 单价可能不存在，置 null
3. 字段不确定时将该条目 uncertain=true
4. 整体置信度 confidence：0-1，全部明确=1.0，有缺失=0.6-0.8
返回 JSON，格式：{format_instructions}"""


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


def _read_file_text(file_path: str) -> str:
    """从本地路径读取文件文本（仅支持 .txt/.csv，xlsx 需预处理）"""
    p = Path(file_path)
    if not p.exists():
        raise ParseError(f"文件不存在：{file_path}")
    suffix = p.suffix.lower()
    if suffix in {".txt", ".csv"}:
        return _decode_bytes(p.read_bytes())
    if suffix == ".xlsx":
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            lines: list[str] = []
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    parts = [str(c) for c in row if c is not None]
                    if parts:
                        lines.append("\t".join(parts))
            return "\n".join(lines)
        except Exception as exc:
            raise ParseError(f"Excel 读取失败：{exc}") from exc
    raise ParseError(f"不支持的文件格式：{suffix}")


def _fallback_parse(raw_text: str) -> PurchaseList:
    """模型不可用时解析标准表头，保证基础清单仍能进入人工核对。"""
    # 有 tab 用 tab：xlsx 转出的文本里千分位逗号（3,180.00）不是分隔符
    delimiter = "\t" if "\t" in raw_text else ","
    rows = list(csv.reader(io.StringIO(raw_text), delimiter=delimiter))
    if not rows:
        raise ParseError("采购清单为空")
    header = [str(value).strip() for value in rows[0]]
    aliases = {
        "species": {"品种", "品名", "名称", "物料名称"},
        "spec": {"规格", "规格型号", "型号"},
        "quantity": {"数量", "采购数量"},
        "unit": {"单位"},
        "unit_price": {"单价", "单价(元)", "含税单价(元)", "单价（元）"},
    }
    indexes = {
        key: next((i for i, value in enumerate(header) if value in names), None)
        for key, names in aliases.items()
    }
    required = ("species", "spec", "quantity", "unit")
    if any(indexes[key] is None for key in required):
        raise ParseError("清单缺少品种、规格、数量或单位列")
    items = []
    for row in rows[1:]:
        if not any(str(value).strip() for value in row):
            continue
        species_index = indexes["species"]
        if species_index is None or species_index >= len(row):
            continue
        species = str(row[species_index]).strip()
        if not species or species in {"合计", "总计", "小计"}:
            continue
        try:
            quantity = float(row[indexes["quantity"]])
        except (ValueError, TypeError, IndexError):
            continue
        if quantity <= 0:
            continue
        price = None
        price_index = indexes["unit_price"]
        if price_index is not None and price_index < len(row):
            try:
                price = float(row[price_index])
            except (ValueError, TypeError):
                pass
        items.append({
            "species": species,
            "spec": str(row[indexes["spec"]]).strip(),
            "quantity": quantity,
            "unit": str(row[indexes["unit"]]).strip(),
            "unit_price": price,
            "uncertain": False,
        })
    if not items:
        raise ParseError("未识别到有效采购项目")
    return PurchaseList(items=items, confidence=0.85)


class ListParserAgent:
    """清单解析 Agent（轻量档，结构化提取）"""

    async def parse(
        self,
        data: ParseInput,
        team_id: int,
        session_id: str,
        db: AsyncSession,
    ) -> ParseResult:
        """解析采购清单，返回结构化 ParseResult"""
        if data.file_path:
            # openpyxl 解析是同步 CPU 操作，放入线程池避免阻塞事件循环
            raw_text = await asyncio.to_thread(_read_file_text, data.file_path)
        elif data.text:
            raw_text = data.text
        else:
            raise ParseError("file_path 和 text 不能同时为空")

        t0 = time.monotonic()
        llm = None
        try:
            from langchain.prompts import ChatPromptTemplate
            from langchain_core.output_parsers import PydanticOutputParser
            from app.services.llm_factory import LLMFactory
            parser = PydanticOutputParser(pydantic_object=PurchaseList)
            prompt = ChatPromptTemplate.from_messages([
                ("system", _SYSTEM_PROMPT),
                ("human", "{text}"),
            ]).partial(format_instructions=parser.get_format_instructions())
            llm = LLMFactory.get_light()
            chain = prompt | llm | parser
            from app.services.llm_gate import LLMGate
            purchase_list: PurchaseList = await LLMGate.run(
                "light", lambda: chain.ainvoke({"text": raw_text[:4000]})
            )
        except Exception as exc:
            logger.warning("清单模型解析失败，尝试表格兜底：%s", exc)
            purchase_list = _fallback_parse(raw_text)

        latency_ms = int((time.monotonic() - t0) * 1000)
        from app.services.llm_logger import LLMCallLogger
        await LLMCallLogger.log(
            agent_name="ListParserAgent",
            model=getattr(llm, "model_name", "fallback-table"),
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            latency_ms=latency_ms,
            cache_hit=False,
            session_id=session_id,
            db=db,
        )

        needs_review = (
            purchase_list.confidence < 0.8
            or any(item.uncertain for item in purchase_list.items)
        )
        return ParseResult(
            purchase_list=purchase_list,
            raw_text=raw_text[:500],
            needs_review=needs_review,
        )
