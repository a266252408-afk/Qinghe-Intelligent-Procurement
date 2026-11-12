"""询价单 Agent 测试：绿化工程量清单模板的版式与内容映射。"""
from pathlib import Path

import openpyxl
import pytest
from openpyxl.utils import get_column_letter

from app.agents.inquiry import InquiryAgent
from app.core.config import settings
from app.core.security import decode_token
from app.schemas.auth import LoginRequest, TeamCreate
from app.schemas.inquiry import InquiryGenerateInput
from app.schemas.order import OrderCreate, OrderItemCreate
from app.schemas.project import ProjectCreate
from app.services.auth_service import AuthService
from app.services.order_service import PurchaseOrderService
from app.services.project_service import ProjectService

pytestmark = pytest.mark.asyncio


async def _setup_order(db, project_name: str = "金科丽苑") -> tuple[int, int]:
    """创建团队/项目/采购单并写入采购项，返回 (team_id, order_id)"""
    token = await AuthService.login_or_register(
        LoginRequest(username="inquiry_user", password="p"), db
    )
    uid = decode_token(token.access_token)["user_id"]
    team = await AuthService.create_team(uid, TeamCreate(name="询价团队"), db)
    project = await ProjectService.create_project(
        ProjectCreate(name=project_name), uid, team.team_id, db
    )
    order = await PurchaseOrderService.create_order(
        OrderCreate(project_id=project.project_id), uid, team.team_id, db
    )
    await PurchaseOrderService.save_items(
        order.order_id,
        [
            OrderItemCreate(
                species="造型黄杨", spec="H1.2m，冠幅0.8m", quantity=2, unit="株"
            ),
            OrderItemCreate(
                species="香水柠檬", spec="胸径8cm，H2m", quantity=1, unit="株",
                unit_price=120.5,
            ),
            OrderItemCreate(
                species="陶粒", spec="粒径10-20mm", quantity=3.5, unit="包",
                unit_price=25,
            ),
        ],
        team.team_id,
        db,
    )
    return team.team_id, order.order_id


async def _generate(db, template_id: str = "greening_boq"):
    team_id, order_id = await _setup_order(db)
    result = await InquiryAgent().generate(
        InquiryGenerateInput(order_id=order_id, template_id=template_id),
        team_id,
        "test-session",
        db,
    )
    return result, Path(settings.UPLOAD_DIR) / result.file_path


async def test_greening_boq_uses_project_name_and_keeps_format(db, tmp_path, monkeypatch):
    """绿化工程量清单模板：B2 用采购单所属项目名，样式与原表一致。"""
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    result, path = await _generate(db)

    assert result.template_id == "greening_boq"
    assert result.template_name == "绿化工程量清单"
    assert path.is_file()

    ws = openpyxl.load_workbook(path).active
    assert ws["B2"].value == "项目名称（金科丽苑）"
    assert ws["A1"].value == "花盆绿化工程分部分项工程量清单及综合单价分析表"

    # 表头样式：绿色底、白字、微软雅黑加粗
    title = ws["A1"]
    assert (title.font.name, title.font.sz, title.font.bold) == ("微软雅黑", 16, True)
    assert title.font.color.rgb == "FFFFFFFF"
    assert title.fill.fgColor.rgb == "FF1E7B3C"
    header = ws["B2"]
    assert (header.font.name, header.font.sz, header.font.bold) == ("微软雅黑", 11, True)
    assert header.fill.fgColor.rgb == "FF1E7B3C"
    assert header.border.left.style == "thin"

    # 合并单元格与列宽、行高
    merges = {str(r) for r in ws.merged_cells.ranges}
    assert {"A1:L1", "A2:A5", "B2:B5", "C2:C5", "D2:D5", "E2:E5",
            "F2:F5", "G2:G5", "H2:H5", "I2:I5", "J2:J5", "K2:K5",
            "L2:L5", "A9:G9"} <= merges
    assert ws.column_dimensions["B"].width == 16
    assert ws.column_dimensions["C"].width == 9
    assert ws.row_dimensions[1].height == 34
    assert ws.row_dimensions[6].height == 30

    # 采购项映射到清单列
    assert [ws.cell(row=6, column=c).value for c in (2, 6, 7, 9, 10)] == [
        "造型黄杨", "H1.2m，冠幅0.8m", "株", 2, None
    ]
    assert ws["J7"].value == 120.5
    assert ws["K6"].value == '=IF(J6="","",I6*J6)'
    assert ws["I8"].value == 3.5
    assert ws["I8"].number_format == "0.##"

    # 明细行样式与合计行样式
    assert (ws["A6"].font.name, ws["A6"].font.sz) == ("宋体", 11)
    assert ws["A6"].border.left.style == "thin"
    assert ws["A6"].border.left.color.rgb == "FF9AA79A"
    total = ws["A9"]
    assert total.value == "合 计"
    assert total.font.bold and total.font.color.rgb == "FF14532D"
    assert total.fill.fgColor.rgb == "FFE8F5E9"
    assert total.border.top.style == "medium"
    assert ws["K9"].value == "=SUM(K6:K8)"

    # 打印版式
    assert ws.page_setup.orientation == "landscape"
    assert ws.page_setup.paperSize == 9
    assert ws.print_area == "'绿化工程量清单及综合单价分析表'!$A$1:$L$9"
    assert ws.print_title_rows == "$1:$5"
    assert ws.auto_filter.ref == "A5:L9"
    assert ws.freeze_panes == "B6"


async def test_greening_boq_expands_rows_for_large_order(db, tmp_path, monkeypatch):
    """采购项超过样例行数时自动扩展明细行，并同步合计与打印区域。"""
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    team_id, order_id = await _setup_order(db)
    await PurchaseOrderService.save_items(
        order_id,
        [
            OrderItemCreate(species=f"植物{i}", spec="H1m", quantity=i, unit="株")
            for i in range(1, 31)
        ],
        team_id,
        db,
    )
    result = await InquiryAgent().generate(
        InquiryGenerateInput(order_id=order_id, template_id="greening_boq"),
        team_id,
        "test-session",
        db,
    )
    ws = openpyxl.load_workbook(Path(settings.UPLOAD_DIR) / result.file_path).active

    assert ws.max_row == 36
    assert ws["B35"].value == "植物30"
    assert ws["A36"].value == "合 计"
    assert ws["K36"].value == "=SUM(K6:K35)"
    assert "A36:G36" in {str(r) for r in ws.merged_cells.ranges}
    assert ws.print_area.endswith("$A$1:$L$36")
    assert ws.auto_filter.ref == "A5:L36"
    assert get_column_letter(ws.max_column) == "L"
