"""API 集成测试：通过 httpx AsyncClient 测试完整 HTTP 请求链路"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.db.base import Base
from app.db.session import get_db
import app.models  # noqa: F401

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# ── 覆盖 DB 依赖 ──────────────────────────────────────────────────────────

_engine = None
_session_factory = None


@pytest_asyncio.fixture(scope="function", autouse=False)
async def override_db():
    """每个测试函数使用独立内存库"""
    global _engine, _session_factory
    _engine = create_async_engine(TEST_DB_URL, echo=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async def _get_test_db():
        async with _session_factory() as session:
            yield session

    from app.main import app
    app.dependency_overrides[get_db] = _get_test_db
    yield
    app.dependency_overrides.clear()
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


@pytest_asyncio.fixture
async def client(override_db):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ── 辅助函数 ──────────────────────────────────────────────────────────────

async def _login(client: AsyncClient, username: str = "testuser", password: str = "pass") -> str:
    resp = await client.post("/api/auth/login", json={"username": username, "password": password})
    if resp.status_code == 401:
        resp = await client.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


async def _auth_headers(client: AsyncClient, username: str = "testuser") -> dict:
    token = await _login(client, username)
    return {"Authorization": f"Bearer {token}"}


async def _setup_team(client: AsyncClient, username: str = "owner") -> tuple[dict, dict]:
    """创建团队，返回 (team_data, headers_with_team_token)"""
    # 先登录获取初始 token
    init_headers = await _auth_headers(client, username)
    resp = await client.post("/api/auth/team", json={"name": "测试团队"}, headers=init_headers)
    assert resp.status_code == 200
    team_data = resp.json()["data"]
    # 使用 create_team 返回的含 team_id 的新 token
    new_token = team_data["access_token"]
    return team_data, {"Authorization": f"Bearer {new_token}"}


# ── 认证接口测试 ──────────────────────────────────────────────────────────

pytestmark = pytest.mark.asyncio


async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "ok"


async def test_login_returns_token(client):
    register = await client.post("/api/auth/register", json={"username": "alice", "password": "secret"})
    assert register.status_code == 200
    resp = await client.post("/api/auth/login", json={"username": "alice", "password": "secret"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()["data"]


async def test_login_unknown_user_does_not_register(client):
    resp = await client.post("/api/auth/login", json={"username": "unknown", "password": "secret"})
    assert resp.status_code == 401


async def test_register_existing_user_rejected(client):
    first = await client.post("/api/auth/register", json={"username": "repeat", "password": "secret"})
    second = await client.post("/api/auth/register", json={"username": "repeat", "password": "secret"})
    assert first.status_code == 200
    assert second.status_code == 409


async def test_me_returns_user_info(client):
    headers = await _auth_headers(client)
    resp = await client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "testuser"


async def test_create_team(client):
    headers = await _auth_headers(client, "newowner")
    resp = await client.post("/api/auth/team", json={"name": "My Team"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["invite_code"]


async def test_join_team(client):
    team_data, owner_headers = await _setup_team(client, "joinowner")
    # 新用户加入
    member_init_headers = await _auth_headers(client, "member1")
    resp = await client.post(
        "/api/auth/team/join",
        json={"invite_code": team_data["invite_code"]},
        headers=member_init_headers,
    )
    assert resp.status_code == 200
    # join_team 现在返回新 Token；role 在 JWT 里，从 /me 验证
    assert "access_token" in resp.json()["data"]


async def test_member_can_leave_team(client):
    """成员退出团队后返回无团队 Token。"""
    team_data, _ = await _setup_team(client, "leave_api_owner")
    member_headers = await _auth_headers(client, "leave_api_member")
    joined = await client.post(
        "/api/auth/team/join",
        json={"invite_code": team_data["invite_code"]},
        headers=member_headers,
    )
    joined_headers = {"Authorization": f"Bearer {joined.json()['data']['access_token']}"}
    left = await client.post("/api/auth/team/leave", headers=joined_headers)
    assert left.status_code == 200
    left_me = await client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {left.json()['data']['access_token']}"
    })
    assert left_me.json()["data"]["team_id"] is None


# ── 项目接口测试 ──────────────────────────────────────────────────────────

async def test_create_and_get_project(client):
    _, headers = await _setup_team(client, "pm1")
    resp = await client.post("/api/projects", json={"name": "绿化A"}, headers=headers)
    assert resp.status_code == 200
    pid = resp.json()["data"]["project_id"]

    resp2 = await client.get(f"/api/projects/{pid}", headers=headers)
    assert resp2.json()["data"]["name"] == "绿化A"


async def test_list_projects(client):
    _, headers = await _setup_team(client, "pm2")
    await client.post("/api/projects", json={"name": "P1"}, headers=headers)
    await client.post("/api/projects", json={"name": "P2"}, headers=headers)
    resp = await client.get("/api/projects", headers=headers)
    assert resp.json()["data"]["total"] == 2


async def test_duplicate_project_name_rejected(client):
    _, headers = await _setup_team(client, "duplicate_project_user")
    first = await client.post("/api/projects", json={"name": "同名"}, headers=headers)
    second = await client.post("/api/projects", json={"name": "同名"}, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 409


async def test_project_requires_team(client):
    headers = await _auth_headers(client, "noTeamUser")
    resp = await client.post("/api/projects", json={"name": "X"}, headers=headers)
    assert resp.status_code == 403


async def test_sessions_restore_and_delete(client):
    _, headers = await _setup_team(client, "session_user")
    project = await client.post("/api/projects", json={"name": "会话项目"}, headers=headers)
    project_id = project.json()["data"]["project_id"]
    created = await client.post(
        "/api/knowledge/sessions",
        json={"project_id": project_id, "title": "历史对话"},
        headers=headers,
    )
    session_id = created.json()["data"]["session_id"]
    listed = await client.get(
        "/api/knowledge/sessions", params={"project_id": project_id}, headers=headers
    )
    assert listed.status_code == 200
    assert listed.json()["data"][0]["session_id"] == session_id
    deleted = await client.delete(f"/api/knowledge/sessions/{session_id}", headers=headers)
    assert deleted.status_code == 200
    listed_again = await client.get(
        "/api/knowledge/sessions", params={"project_id": project_id}, headers=headers
    )
    assert listed_again.json()["data"] == []


async def test_delete_project_endpoint(client):
    _, headers = await _setup_team(client, "delete_project_user")
    created = await client.post("/api/projects", json={"name": "待删除项目"}, headers=headers)
    project_id = created.json()["data"]["project_id"]
    deleted = await client.delete(f"/api/projects/{project_id}", headers=headers)
    assert deleted.status_code == 200
    detail = await client.get(f"/api/projects/{project_id}", headers=headers)
    assert detail.status_code == 404


async def test_member_cannot_modify_or_delete_project(client):
    """团队成员可共享项目，但项目管理操作仅限管理员。"""
    team_data, owner_headers = await _setup_team(client, "project_permission_owner")
    member_headers = await _auth_headers(client, "project_permission_member")
    joined = await client.post(
        "/api/auth/team/join",
        json={"invite_code": team_data["invite_code"]},
        headers=member_headers,
    )
    member_headers = {"Authorization": f"Bearer {joined.json()['data']['access_token']}"}
    created = await client.post("/api/projects", json={"name": "共享项目"}, headers=owner_headers)
    project_id = created.json()["data"]["project_id"]

    updated = await client.patch(
        f"/api/projects/{project_id}", json={"name": "成员修改"}, headers=member_headers
    )
    deleted = await client.delete(f"/api/projects/{project_id}", headers=member_headers)
    assert updated.status_code == 403
    assert deleted.status_code == 403


async def test_delete_project_after_same_name_was_deleted(client):
    """软删除同名历史项目后，新项目也必须可以正常删除。"""
    _, headers = await _setup_team(client, "delete_duplicate_project_user")
    first = await client.post("/api/projects", json={"name": "重复删除测试"}, headers=headers)
    first_id = first.json()["data"]["project_id"]
    assert (await client.delete(f"/api/projects/{first_id}", headers=headers)).status_code == 200
    second = await client.post("/api/projects", json={"name": "重复删除测试"}, headers=headers)
    second_id = second.json()["data"]["project_id"]
    deleted = await client.delete(f"/api/projects/{second_id}", headers=headers)
    assert deleted.status_code == 200


async def test_admin_invites_purchaser_and_purchaser_accepts(client):
    """采购员没有团队，收到管理员邀请并同意后才加入。"""
    admin = await client.post(
        "/api/auth/register",
        json={"username": "invite_admin", "password": "secret", "account_type": "admin", "team_name": "邀请团队"},
    )
    assert admin.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin.json()['data']['access_token']}"}
    purchaser = await client.post(
        "/api/auth/register",
        json={"username": "invite_purchaser", "password": "secret", "account_type": "purchaser"},
    )
    assert purchaser.status_code == 200
    purchaser_headers = {"Authorization": f"Bearer {purchaser.json()['data']['access_token']}"}
    no_team = await client.get("/api/auth/me", headers=purchaser_headers)
    assert no_team.json()["data"]["team_id"] is None

    sent = await client.post(
        "/api/auth/team/invitations",
        json={"username": "invite_purchaser"},
        headers=admin_headers,
    )
    assert sent.status_code == 200
    invitation_id = sent.json()["data"]["invitation_id"]
    incoming = await client.get("/api/auth/team/invitations", headers=purchaser_headers)
    assert incoming.json()["data"][0]["team_name"] == "邀请团队"
    accepted = await client.post(
        f"/api/auth/team/invitations/{invitation_id}/accept", headers=purchaser_headers
    )
    assert accepted.status_code == 200
    joined_headers = {"Authorization": f"Bearer {accepted.json()['data']['access_token']}"}
    joined = await client.get("/api/auth/me", headers=joined_headers)
    assert joined.json()["data"]["team_name"] == "邀请团队"
    assert joined.json()["data"]["role"] == "member"


# ── 采购单接口测试 ────────────────────────────────────────────────────────

async def test_create_order_and_submit(client):
    _, headers = await _setup_team(client, "orduser")
    proj_resp = await client.post("/api/projects", json={"name": "Test"}, headers=headers)
    pid = proj_resp.json()["data"]["project_id"]

    # 创建采购单
    resp = await client.post("/api/orders", json={"project_id": pid}, headers=headers)
    assert resp.status_code == 200
    oid = resp.json()["data"]["order_id"]
    assert resp.json()["data"]["status"] == "draft"

    # 保存采购项
    items = [{"species": "香樟", "spec": "胸径15cm", "quantity": 5, "unit": "株"}]
    await client.put(f"/api/orders/{oid}/items", json=items, headers=headers)

    # 提交审批
    resp2 = await client.post(f"/api/orders/{oid}/submit", headers=headers)
    assert resp2.json()["data"]["status"] == "pending_approval"


async def test_update_order_name(client):
    """采购单草稿可保存自定义名称。"""
    _, headers = await _setup_team(client, "update_order_name")
    project = await client.post("/api/projects", json={"name": "命名项目"}, headers=headers)
    order = await client.post(
        "/api/orders",
        json={"project_id": project.json()["data"]["project_id"]},
        headers=headers,
    )
    order_id = order.json()["data"]["order_id"]
    updated = await client.put(
        f"/api/orders/{order_id}",
        json={"name": "第一批苗木采购"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "第一批苗木采购"


async def test_inquiry_available_before_order_approval(client):
    """询价单生成不依赖下单审批状态。"""
    _, headers = await _setup_team(client, "inquiry_before_approval")
    project = await client.post("/api/projects", json={"name": "询价项目"}, headers=headers)
    order = await client.post(
        "/api/orders",
        json={"project_id": project.json()["data"]["project_id"]},
        headers=headers,
    )
    order_id = order.json()["data"]["order_id"]
    await client.put(
        f"/api/orders/{order_id}/items",
        json=[{"species": "香樟", "spec": "胸径12cm", "quantity": 1, "unit": "株"}],
        headers=headers,
    )
    generated = await client.post(
        f"/api/orders/{order_id}/inquiry",
        json={"order_id": order_id, "template_id": "standard"},
        headers=headers,
    )
    assert generated.status_code == 200
    downloaded = await client.get(f"/api/orders/{order_id}/inquiry/download", headers=headers)
    assert downloaded.status_code == 200


async def test_submit_empty_order_422(client):
    _, headers = await _setup_team(client, "emptyuser")
    proj_resp = await client.post("/api/projects", json={"name": "P"}, headers=headers)
    pid = proj_resp.json()["data"]["project_id"]
    resp = await client.post("/api/orders", json={"project_id": pid}, headers=headers)
    oid = resp.json()["data"]["order_id"]

    resp2 = await client.post(f"/api/orders/{oid}/submit", headers=headers)
    assert resp2.status_code == 422


async def test_non_draft_order_items_cannot_be_overwritten(client):
    """进入审批后的采购单不能被清单确认流程覆盖。"""
    _, headers = await _setup_team(client, "locked_order_user")
    project = await client.post("/api/projects", json={"name": "锁定项目"}, headers=headers)
    order = await client.post(
        "/api/orders", json={"project_id": project.json()["data"]["project_id"]}, headers=headers
    )
    order_id = order.json()["data"]["order_id"]
    items = [{"species": "香樟", "spec": "胸径12cm", "quantity": 1, "unit": "株"}]
    await client.put(f"/api/orders/{order_id}/items", json=items, headers=headers)
    await client.post(f"/api/orders/{order_id}/submit", headers=headers)
    overwritten = await client.put(f"/api/orders/{order_id}/items", json=items, headers=headers)
    assert overwritten.status_code == 422


# ── 审批接口测试 ──────────────────────────────────────────────────────────

async def test_approve_flow(client):
    _, headers = await _setup_team(client, "appruser")
    proj_resp = await client.post("/api/projects", json={"name": "P"}, headers=headers)
    pid = proj_resp.json()["data"]["project_id"]

    ord_resp = await client.post("/api/orders", json={"project_id": pid}, headers=headers)
    oid = ord_resp.json()["data"]["order_id"]
    items = [{"species": "松树", "spec": "高3m", "quantity": 2, "unit": "棵"}]
    await client.put(f"/api/orders/{oid}/items", json=items, headers=headers)
    await client.post(f"/api/orders/{oid}/submit", headers=headers)

    # 列表
    list_resp = await client.get("/api/approvals", headers=headers)
    assert list_resp.json()["data"]["total"] == 1
    pending = list_resp.json()["data"]["items"][0]
    assert pending["creator_name"] == "appruser"
    assert pending["project_name"] == "P"
    assert pending["total_amount"] is None

    # 通过
    approve_resp = await client.post(f"/api/approvals/{oid}/approve", headers=headers)
    assert approve_resp.json()["data"]["decision"] == "approved"


async def test_supplier_order_list_and_download(client):
    """下单审批通过后可查询下单记录并下载 CSV/Excel。"""
    _, headers = await _setup_team(client, "supplier_order_user")
    project = await client.post("/api/projects", json={"name": "下单项目"}, headers=headers)
    pid = project.json()["data"]["project_id"]
    order = await client.post("/api/orders", json={"project_id": pid}, headers=headers)
    oid = order.json()["data"]["order_id"]
    await client.put(
        f"/api/orders/{oid}/items",
        json=[{"species": "香樟", "spec": "胸径12cm", "quantity": 2, "unit": "株"}],
        headers=headers,
    )
    await client.post(f"/api/orders/{oid}/submit", headers=headers)
    approved = await client.post(f"/api/approvals/{oid}/approve", headers=headers)
    assert approved.status_code == 200

    listed = await client.get("/api/orders/supplier-orders", headers=headers)
    assert listed.status_code == 200
    supplier_order_id = listed.json()["data"][0]["supplier_order_id"]
    assert listed.json()["data"][0]["items"][0]["species"] == "香樟"

    csv_resp = await client.get(
        f"/api/orders/supplier-orders/{supplier_order_id}/download",
        params={"file_format": "csv"},
        headers=headers,
    )
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "香樟" in csv_resp.content.decode("utf-8-sig")

    excel_resp = await client.get(
        f"/api/orders/supplier-orders/{supplier_order_id}/download",
        params={"file_format": "xlsx"},
        headers=headers,
    )
    assert excel_resp.status_code == 200
    assert excel_resp.content[:2] == b"PK"


async def test_management_delete_requires_owner(client):
    """下单和收货管理删除接口仅管理员可用。"""
    team_data, owner_headers = await _setup_team(client, "management_delete_owner")
    member_headers = await _auth_headers(client, "management_delete_member")
    joined = await client.post(
        "/api/auth/team/join",
        json={"invite_code": team_data["invite_code"]},
        headers=member_headers,
    )
    member_headers = {"Authorization": f"Bearer {joined.json()['data']['access_token']}"}

    project = await client.post("/api/projects", json={"name": "删除权限项目"}, headers=owner_headers)
    order = await client.post(
        "/api/orders",
        json={"project_id": project.json()["data"]["project_id"]},
        headers=owner_headers,
    )
    order_id = order.json()["data"]["order_id"]
    await client.put(
        f"/api/orders/{order_id}/items",
        json=[{"species": "香樟", "spec": "胸径12cm", "quantity": 1, "unit": "株"}],
        headers=owner_headers,
    )
    await client.post(f"/api/orders/{order_id}/submit", headers=owner_headers)
    await client.post(f"/api/approvals/{order_id}/approve", headers=owner_headers)
    supplier_orders = await client.get("/api/orders/supplier-orders", headers=owner_headers)
    supplier_order_id = supplier_orders.json()["data"][0]["supplier_order_id"]
    receipts = await client.get("/api/receipts", headers=owner_headers)
    receipt_id = receipts.json()["data"][0]["receipt_id"]

    assert (await client.delete(f"/api/orders/supplier-orders/{supplier_order_id}", headers=member_headers)).status_code == 403
    assert (await client.delete(f"/api/receipts/{receipt_id}", headers=member_headers)).status_code == 403
    assert (await client.delete(f"/api/receipts/{receipt_id}", headers=owner_headers)).status_code == 200
    assert (await client.delete(f"/api/orders/supplier-orders/{supplier_order_id}", headers=owner_headers)).status_code == 200
    assert (await client.get("/api/orders/supplier-orders", headers=owner_headers)).json()["data"] == []


async def test_chat_expired_route_confirm_returns_410(client, monkeypatch):
    """续跑前预检过期的待确认 token，必须在 SSE 开始前返回 410。"""
    from datetime import datetime, timedelta, timezone

    import app.db.session as session_module
    from app.models.knowledge import Message

    # /api/chat 自管数据库会话（SSE 防连接泄漏），测试需把工厂指向内存库
    monkeypatch.setattr(session_module, "AsyncSessionLocal", _session_factory)
    _, headers = await _setup_team(client, "routeowner")
    session_resp = await client.post(
        "/api/knowledge/sessions", json={"title": "路由确认"}, headers=headers
    )
    session_id = session_resp.json()["data"]["session_id"]

    expired = datetime.now(timezone.utc) - timedelta(hours=1)
    async with _session_factory() as db:
        db.add(Message(
            session_id=session_id,
            role="assistant",
            content="请确认路由",
            metadata_json={
                "structured_type": "route_confirm",
                "structured_data": {
                    "status": "pending",
                    "token": "expired-token",
                    "message": "香樟怎么处理",
                    "user_message_id": 1,
                    "options": [],
                    "created_at": expired.isoformat(),
                    "ttl_minutes": 30,
                },
            },
        ))
        await db.commit()

    resp = await client.post("/api/chat", json={
        "message": "ignored", "session_id": session_id,
        "forced_intent": "chat", "pending_token": "expired-token",
    }, headers=headers)

    assert resp.status_code == 410
    assert resp.json()["code"] == 410


async def test_reject_without_reason_422(client):
    _, headers = await _setup_team(client, "rejuser")
    proj_resp = await client.post("/api/projects", json={"name": "P"}, headers=headers)
    pid = proj_resp.json()["data"]["project_id"]
    ord_resp = await client.post("/api/orders", json={"project_id": pid}, headers=headers)
    oid = ord_resp.json()["data"]["order_id"]
    items = [{"species": "桂花", "spec": "高2m", "quantity": 3, "unit": "棵"}]
    await client.put(f"/api/orders/{oid}/items", json=items, headers=headers)
    await client.post(f"/api/orders/{oid}/submit", headers=headers)

    # 驳回不带原因
    resp = await client.post(f"/api/approvals/{oid}/reject", json={"reason": ""}, headers=headers)
    assert resp.status_code == 422
