"""询价单生成 Agent：从采购单生成 Excel 询价模板
依据：docs/module-sdd/inquiry_agent.md
"""
import asyncio
import copy
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NoQuoteError, TemplateNotFoundError
from app.models.order import PurchaseOrder, PurchaseItem
from app.schemas.inquiry import InquiryGenerateInput, InquiryResult, TemplateInfo
from app.services.order_service import PurchaseOrderService
from app.services.quote_service import QuoteService

logger = logging.getLogger(__name__)

_TEMPLATES: dict[str, TemplateInfo] = {
    "standard":       TemplateInfo(template_id="standard",       name="标准询价单",   description="含单价/数量/规格/备注"),
    "simple":         TemplateInfo(template_id="simple",         name="简化询价单",   description="仅品种/数量"),
    "with_delivery":  TemplateInfo(template_id="with_delivery",  name="含交期询价单", description="增加交货期/付款条件列"),
    "greening_boq":   TemplateInfo(
        template_id="greening_boq",
        name="绿化工程量清单",
        description="参照花箱绿化工程量清单版式，含规格/工程量/综合单价/综合合价及合计",
    ),
}

_HEADER_FILL = PatternFill("solid", fgColor="4472C4")
_HEADER_FONT = Font(color="FFFFFF", bold=True)

# 绿化工程量清单模板：底版文件与固定版式坐标（表头 1-5 行，明细从第 6 行开始）
_BOQ_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "greening_boq.xlsx"
_BOQ_DATA_START_ROW = 6
_BOQ_COLUMN_COUNT = 12


class InquiryAgent:
    """询价单生成 Agent（无需调用 LLM，确定性生成）"""

    def list_templates(self) -> list[TemplateInfo]:
        """返回可用模板列表"""
        return list(_TEMPLATES.values())

    async def generate(
        self,
        data: InquiryGenerateInput,
        team_id: int,
        session_id: str,
        db: AsyncSession,
    ) -> InquiryResult:
        """根据采购单生成 Excel 询价模板，保存文件并写 inquiry_sheets 记录"""
        if data.template_id not in _TEMPLATES:
            raise TemplateNotFoundError(f"模板 {data.template_id} 不存在")

        # 加载采购单及所属项目名称（数据访问归 order_service）
        order, project_name = await PurchaseOrderService.get_order_with_project_scoped(
            data.order_id, team_id, db
        )
        if not order.items:
            raise NoQuoteError()

        # openpyxl 写 Excel 是同步 CPU 操作，放线程池避免阻塞事件循环
        file_path = await asyncio.to_thread(
            self._write_excel, order, data.template_id, team_id, project_name
        )

        # 写 inquiry_sheets 记录（持久化归 quote_service）
        sheet = await QuoteService.create_inquiry_sheet(
            data.order_id, data.template_id, file_path, db)

        preview_items = [
            {"species": i.species, "spec": i.spec, "quantity": float(i.quantity), "unit": i.unit}
            for i in order.items[:5]
        ]
        return InquiryResult(
            inquiry_id=sheet.id,
            file_path=file_path,
            filename=Path(file_path).name,
            preview_items=preview_items,
            template_id=data.template_id,
            template_name=_TEMPLATES[data.template_id].name,
            download_url=f"/api/orders/{data.order_id}/inquiry/download",
        )

    def _write_excel(
        self,
        order: PurchaseOrder,
        template_id: str,
        team_id: int,
        project_name: str = "",
    ) -> str:
        """将采购项写入 Excel，返回相对文件路径（同步函数，调用方需经线程池执行）"""
        if template_id == "greening_boq":
            wb = _build_greening_boq(order, project_name)
        else:
            wb = _build_default_template(order, template_id)
        return _save_workbook(wb, order.id, team_id)


def _build_default_template(order: PurchaseOrder, template_id: str) -> openpyxl.Workbook:
    """构建原有三类询价单（标准/简化/含交期）"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "询价单"

    headers = _get_headers(template_id)
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center")

    for row_idx, item in enumerate(order.items, 2):
        _write_row(ws, row_idx, item, template_id)
    return wb


def _save_workbook(wb: openpyxl.Workbook, order_id: int, team_id: int) -> str:
    """保存工作簿到团队上传目录，返回相对路径"""
    now = datetime.now()
    rel_dir = Path(str(team_id)) / "inquiry" / now.strftime("%Y/%m")
    abs_dir = Path(settings.UPLOAD_DIR) / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    filename = f"inquiry_{order_id}_{uuid.uuid4().hex[:8]}.xlsx"
    abs_path = abs_dir / filename
    wb.save(str(abs_path))
    return str(rel_dir / filename)


def _build_greening_boq(order: PurchaseOrder, project_name: str) -> openpyxl.Workbook:
    """以样例 Excel 为底版重建明细行，完整保留原表样式与打印版式"""
    if not _BOQ_TEMPLATE_PATH.is_file():
        raise TemplateNotFoundError("绿化工程量清单模板文件缺失")

    wb = openpyxl.load_workbook(_BOQ_TEMPLATE_PATH)
    ws = wb.active
    data_styles = _capture_row_styles(ws, _BOQ_DATA_START_ROW)
    total_styles = _capture_row_styles(ws, ws.max_row)
    data_height = ws.row_dimensions[_BOQ_DATA_START_ROW].height or 30
    total_height = ws.row_dimensions[ws.max_row].height or 30

    _clear_boq_body(ws)
    for offset, item in enumerate(order.items):
        _write_boq_item_row(
            ws, _BOQ_DATA_START_ROW + offset, item, data_styles, data_height
        )

    total_row = _BOQ_DATA_START_ROW + len(order.items)
    _write_boq_total_row(ws, total_row, total_styles, total_height)
    _update_boq_layout(ws, total_row)
    ws["B2"] = _project_header(project_name)
    wb.calculation.fullCalcOnLoad = True
    return wb


def _capture_row_styles(ws: Any, row: int) -> list[Any]:
    """复制某一行的单元格样式快照，供重建行时逐格复原"""
    return [
        copy.copy(ws.cell(row=row, column=col)._style)
        for col in range(1, _BOQ_COLUMN_COUNT + 1)
    ]


def _clear_boq_body(ws: Any) -> None:
    """解除明细区合并单元格并删除样例明细，保留表头 1-5 行"""
    for cell_range in list(ws.merged_cells.ranges):
        if cell_range.min_row >= _BOQ_DATA_START_ROW:
            ws.unmerge_cells(str(cell_range))
    ws.delete_rows(_BOQ_DATA_START_ROW, ws.max_row - _BOQ_DATA_START_ROW + 1)


def _write_boq_item_row(
    ws: Any, row: int, item: PurchaseItem, styles: list[Any], height: float
) -> None:
    """把采购项写入清单行：B=项目名称，F=备注(规格)，G=单位，I=数量，J=综合单价"""
    unit_price = float(item.unit_price) if item.unit_price is not None else None
    values = [
        None,                      # A 位置：采购单无位置信息，留空待填
        item.species,              # B 项目名称
        None,                      # C 自然高度：采购单仅有自由文本规格
        None,                      # D 冠幅
        None,                      # E 胸径
        item.spec,                 # F 备注：保留采购单规格原文
        item.unit,                 # G 单位
        None,                      # H 工程量
        float(item.quantity),      # I 数量
        unit_price,                # J 综合单价
        None,                      # K 综合合价（下方写公式）
        None,                      # L 备注
    ]
    for col, (value, style) in enumerate(zip(values, styles), 1):
        cell = ws.cell(row=row, column=col, value=value)
        cell._style = copy.copy(style)

    quantity_cell = ws.cell(row=row, column=9)
    if not float(item.quantity).is_integer():
        quantity_cell.number_format = "0.##"
    # 单价为空时不显示 0，填入单价后自动计算合价
    ws.cell(row=row, column=11, value=f'=IF(J{row}="","",I{row}*J{row})')
    ws.row_dimensions[row].height = height


def _write_boq_total_row(
    ws: Any, row: int, styles: list[Any], height: float
) -> None:
    """重建合计行：A:G 合并、K 列汇总，样式复用原合计行"""
    for col, style in enumerate(styles, 1):
        cell = ws.cell(row=row, column=col)
        cell._style = copy.copy(style)
    ws.cell(row=row, column=1, value="合 计")
    ws.cell(
        row=row,
        column=11,
        value=f"=SUM(K{_BOQ_DATA_START_ROW}:K{row - 1})",
    )
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=7)
    ws.row_dimensions[row].height = height


def _update_boq_layout(ws: Any, total_row: int) -> None:
    """同步打印区域、重复表头、筛选范围等版式坐标"""
    ws.print_area = f"A1:L{total_row}"
    ws.print_title_rows = "1:5"
    ws.auto_filter.ref = f"A5:L{total_row}"
    ws.freeze_panes = "B6"


def _project_header(project_name: str) -> str:
    """表头 B2 使用采购单所属项目名称，保持原表括号写法"""
    name = (project_name or "").strip()
    return f"项目名称（{name}）" if name else "项目名称"


def _get_headers(template_id: str) -> list[str]:
    base = ["序号", "品种", "规格", "数量", "单位", "单价（元）", "备注"]
    if template_id == "simple":
        return ["序号", "品种", "数量", "单位"]
    if template_id == "with_delivery":
        return base + ["交货天数", "付款条件"]
    return base


def _write_row(ws: Any, row: int, item: PurchaseItem, template_id: str) -> None:
    seq = row - 1
    if template_id == "simple":
        ws.cell(row=row, column=1, value=seq)
        ws.cell(row=row, column=2, value=item.species)
        ws.cell(row=row, column=3, value=float(item.quantity))
        ws.cell(row=row, column=4, value=item.unit)
    else:
        ws.cell(row=row, column=1, value=seq)
        ws.cell(row=row, column=2, value=item.species)
        ws.cell(row=row, column=3, value=item.spec)
        ws.cell(row=row, column=4, value=float(item.quantity))
        ws.cell(row=row, column=5, value=item.unit)
        ws.cell(row=row, column=6, value=None)  # 单价待填
        ws.cell(row=row, column=7, value=None)  # 备注
        if template_id == "with_delivery":
            ws.cell(row=row, column=8, value=None)  # 交货天数
            ws.cell(row=row, column=9, value=None)  # 付款条件
