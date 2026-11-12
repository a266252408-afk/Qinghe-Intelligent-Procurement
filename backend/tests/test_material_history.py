"""长期材料历史与报价确认联动测试。"""
from datetime import date

import pytest
from sqlalchemy import select

from app.models.material_history import MaterialHistoryRecord
from app.models.quote import Quote, QuoteItem
from app.services.auth_service import AuthService
from app.services.material_history import MaterialHistoryService
from app.services.order_service import PurchaseOrderService
from app.services.project_service import ProjectService
from app.services.quote_service import QuoteService
from app.schemas.auth import LoginRequest, TeamCreate
from app.schemas.order import OrderCreate, OrderItemCreate
from app.schemas.project import ProjectCreate
from app.schemas.quote import QuoteCreateInput, QuoteItemInput
from app.schemas.material_history import MaterialHistoryFilter
from app.core.security import decode_token

pytestmark = pytest.mark.asyncio


async def _setup_order(db, username: str) -> tuple[int, int, int]:
    """创建测试用户、团队、项目和草稿采购单。"""
    token = await AuthService.login_or_register(
        LoginRequest(username=username, password="p"), db
    )
    user_id = decode_token(token.access_token)["user_id"]
    team = await AuthService.create_team(user_id, TeamCreate(name=f"团队-{username}"), db)
    project = await ProjectService.create_project(
        ProjectCreate(name=f"项目-{username}"), user_id, team.team_id, db
    )
    order = await PurchaseOrderService.create_order(
        OrderCreate(project_id=project.project_id), user_id, team.team_id, db
    )
    return user_id, team.team_id, order.order_id


def _quote_data(upload_id: int, path: str, quote_date: date) -> QuoteCreateInput:
    """构造报价确认输入，明确区分报价价和成交价。"""
    return QuoteCreateInput(
        order_id=1,
        supplier_name="示例园林",
        file_path=path,
        original_name="报价.csv",
        upload_id=upload_id,
        quote_date=quote_date,
        items=[
            QuoteItemInput(
                species="香樟",
                spec="胸径12cm",
                unit="株",
                quantity=10,
                unit_price=860,
                final_price=840,
            )
        ],
    )


async def test_confirm_quote_writes_history_and_deduplicates(db, monkeypatch):
    """报价管理保存成功，同时长期记忆同字段重复只保留一条。"""
    async def skip_vector_index(_record):
        return None

    monkeypatch.setattr("app.services.material_history._index_record", skip_vector_index)
    user_id, team_id, order_id = await _setup_order(db, "history_user")
    path = "1/quote/quote.csv"

    upload = await QuoteService.register_upload(team_id, user_id, path, "报价.csv", db)
    first = await QuoteService.create(
        _quote_data(upload.id, path, date(2026, 8, 25)).model_copy(update={"order_id": order_id}),
        team_id,
        db,
        user_id,
    )
    duplicate_upload = await QuoteService.register_upload(team_id, user_id, path, "报价.csv", db)
    second = await QuoteService.create(
        _quote_data(duplicate_upload.id, path, date(2026, 8, 25)).model_copy(update={"order_id": order_id}),
        team_id,
        db,
        user_id,
    )

    records = (await db.execute(
        select(MaterialHistoryRecord).where(MaterialHistoryRecord.team_id == team_id)
    )).scalars().all()
    assert first.items[0].unit_price == 860
    assert first.items[0].final_price == 840
    assert second.quote_id != first.quote_id
    assert len(records) == 1
    assert records[0].quote_price == 860
    assert records[0].final_price == 840
    assert records[0].uploaded_by == user_id
    assert records[0].confirmed_by == user_id


async def test_history_keeps_same_material_on_different_dates(db, monkeypatch):
    """相同材料在不同报价日期属于不同历史记录。"""
    async def skip_vector_index(_record):
        return None

    monkeypatch.setattr("app.services.material_history._index_record", skip_vector_index)
    user_id, team_id, order_id = await _setup_order(db, "history_date_user")
    for index, quote_date in enumerate((date(2026, 8, 1), date(2026, 8, 2))):
        path = f"1/quote/{index}.csv"
        upload = await QuoteService.register_upload(team_id, user_id, path, "报价.csv", db)
        data = _quote_data(upload.id, path, quote_date).model_copy(update={"order_id": order_id})
        await QuoteService.create(data, team_id, db, user_id)

    records = await MaterialHistoryService.list_records(
        filters=MaterialHistoryFilter(),
        team_id=team_id,
        db=db,
    )
    assert len(records) == 2
    assert {record.quote_date for record in records} == {date(2026, 8, 1), date(2026, 8, 2)}


async def test_history_isolated_by_team(db, monkeypatch):
    """长期材料历史不能跨团队读取。"""
    async def skip_vector_index(_record):
        return None

    monkeypatch.setattr("app.services.material_history._index_record", skip_vector_index)
    user_id, team_id, order_id = await _setup_order(db, "history_team_a")
    path = "1/quote/team-a.csv"
    upload = await QuoteService.register_upload(team_id, user_id, path, "报价.csv", db)
    await QuoteService.create(
        _quote_data(upload.id, path, date(2026, 8, 25)).model_copy(update={"order_id": order_id}),
        team_id,
        db,
        user_id,
    )

    own_records = await MaterialHistoryService.list_records(MaterialHistoryFilter(), team_id, db)
    other_records = await MaterialHistoryService.list_records(MaterialHistoryFilter(), team_id + 999, db)
    assert len(own_records) == 1
    assert other_records == []


async def test_delete_quote_keeps_history(db, monkeypatch):
    """删除报价管理记录时，长期历史仍可查询。"""
    async def skip_vector_index(_record):
        return None

    monkeypatch.setattr("app.services.material_history._index_record", skip_vector_index)
    user_id, team_id, order_id = await _setup_order(db, "delete_quote_user")
    path = "1/quote/delete.csv"
    upload = await QuoteService.register_upload(team_id, user_id, path, "报价.csv", db)
    quote = await QuoteService.create(
        _quote_data(upload.id, path, date(2026, 8, 25)).model_copy(update={"order_id": order_id}),
        team_id,
        db,
        user_id,
    )

    await QuoteService.delete(quote.quote_id, team_id, db)

    assert await db.scalar(select(Quote).where(Quote.id == quote.quote_id)) is None
    assert await db.scalar(select(QuoteItem).where(QuoteItem.quote_id == quote.quote_id)) is None
    record = await db.scalar(select(MaterialHistoryRecord).where(MaterialHistoryRecord.team_id == team_id))
    assert record is not None
    assert record.source_quote_id is None


async def test_delete_quote_releases_purchase_item_reference(db, monkeypatch):
    """删除报价时解除采购项对报价项的引用，不触发外键违例。"""
    async def skip_vector_index(_record):
        return None

    monkeypatch.setattr("app.services.material_history._index_record", skip_vector_index)
    user_id, team_id, order_id = await _setup_order(db, "delete_quote_ref_user")
    path = "1/quote/ref.csv"
    upload = await QuoteService.register_upload(team_id, user_id, path, "报价.csv", db)
    quote = await QuoteService.create(
        _quote_data(upload.id, path, date(2026, 8, 25)).model_copy(update={"order_id": order_id}),
        team_id,
        db,
        user_id,
    )
    quote_item_id = quote.items[0].quote_item_id
    await PurchaseOrderService.save_items(
        order_id,
        [OrderItemCreate(
            species="香樟", spec="胸径12cm", quantity=10, unit="株",
            supplier_name="示例园林",
            supplier_quote_item_id=quote_item_id,
            supplier_quote_price=860,
        )],
        team_id, db,
    )

    await QuoteService.delete(quote.quote_id, team_id, db)
    await db.flush()

    from app.models.order import PurchaseItem
    item = await db.scalar(select(PurchaseItem).where(PurchaseItem.order_id == order_id))
    assert item.supplier_quote_item_id is None


async def test_chat_history_search_uses_exact_team_filtered_records(db, monkeypatch):
    """对话工具查询长期记忆时按材料名称返回当前团队结构化记录。"""
    async def skip_vector_index(_record):
        return None

    monkeypatch.setattr("app.services.material_history._index_record", skip_vector_index)
    user_id, team_id, order_id = await _setup_order(db, "history_chat_user")
    upload = await QuoteService.register_upload(team_id, user_id, "1/quote/chat.csv", "报价.csv", db)
    await QuoteService.create(
        _quote_data(upload.id, "1/quote/chat.csv", date(2026, 8, 25)).model_copy(update={"order_id": order_id}),
        team_id,
        db,
        user_id,
    )

    records = await MaterialHistoryService.search_for_chat("香樟", team_id, db)
    other_team_records = await MaterialHistoryService.search_for_chat("香樟", team_id + 999, db)

    assert len(records) == 1
    assert records[0].material_name == "香樟"
    assert records[0].final_price == 840
    assert other_team_records == []


async def test_history_records_carry_project_and_filter(db, monkeypatch):
    """长期记忆记录携带项目归属，列表返回项目名且支持按项目筛选。"""
    async def skip_vector_index(_record):
        return None

    monkeypatch.setattr("app.services.material_history._index_record", skip_vector_index)
    user_id, team_id, order_id = await _setup_order(db, "history_project_user")
    path = "1/quote/project.csv"
    upload = await QuoteService.register_upload(team_id, user_id, path, "报价.csv", db)
    await QuoteService.create(
        _quote_data(upload.id, path, date(2026, 8, 25)).model_copy(update={"order_id": order_id}),
        team_id,
        db,
        user_id,
    )

    records = await MaterialHistoryService.list_records(MaterialHistoryFilter(), team_id, db)
    assert len(records) == 1
    assert records[0].project_id is not None
    assert records[0].project_name == "项目-history_project_user"

    # 按项目筛选命中
    filtered = await MaterialHistoryService.list_records(
        MaterialHistoryFilter(project_id=records[0].project_id), team_id, db
    )
    assert len(filtered) == 1

    # 其他项目筛选不命中
    miss = await MaterialHistoryService.list_records(
        MaterialHistoryFilter(project_id=records[0].project_id + 999), team_id, db
    )
    assert miss == []
