"""知识库路由：行业文档上传、行业知识检索、知识录入、会话管理"""
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_team_id
from app.core.response import APIResponse
from app.schemas.auth import UserInfo
from app.schemas.knowledge import SessionCreate
from app.schemas.knowledge_agent import KnowledgeQueryInput, KnowledgeRecordExtract, KnowledgeSaveInput, KnowledgeSaveResult
from app.schemas.material_history import MaterialHistoryFilter
from app.services.material_history import MaterialHistoryService
from app.services.knowledge_base import KnowledgeBaseManager
from app.storage.local_storage import local_storage

router = APIRouter()


@router.get("/history", summary="查询长期材料历史")
async def list_material_history(
    filters: MaterialHistoryFilter = Depends(),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """查询当前团队的供应商材料报价与成交价历史。"""
    records = await MaterialHistoryService.list_records(filters, team_id, db)
    return APIResponse.ok([record.model_dump(mode="json") for record in records])


# ── 行业文档上传 ──────────────────────────────────────────────────────────

@router.get("/industry/documents", summary="已上传行业文档列表")
async def list_industry_documents(
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """按来源文件汇总当前团队已上传的行业文档及知识分块数。"""
    if current_user.role != "owner":
        from app.core.exceptions import PermissionDeniedError
        raise PermissionDeniedError("只有团队管理员可以维护行业知识库")
    docs = await KnowledgeBaseManager.list_industry_docs(team_id, db)
    return APIResponse.ok(docs)


@router.post("/industry/upload", summary="上传行业知识文档")
async def upload_industry_doc(
    file: UploadFile = File(...),
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    if current_user.role != "owner":
        from app.core.exceptions import PermissionDeniedError
        raise PermissionDeniedError("只有团队管理员可以维护行业知识库")
    stored = await local_storage.save(file, team_id, "knowledge")
    content = await _read_knowledge_content(stored.path)
    records = await KnowledgeBaseManager.upload_industry_doc(
        team_id, stored.original_name, content, db
    )
    await db.commit()
    return APIResponse.ok({
        "id": records[0].id,
        "source_file": records[0].source_file,
        "chunks": len(records),
    })


# ── 检索 ──────────────────────────────────────────────────────────────────

@router.get("/search", summary="检索行业知识库")
async def search(
    q: str,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    from app.agents.knowledge import KnowledgeAgent
    result = await KnowledgeAgent().query(
        KnowledgeQueryInput(question=q, session_id=""),
        team_id=team_id,
        db=db,
    )
    return APIResponse.ok(result.model_dump())


# ── 知识录入（两步流） ────────────────────────────────────────────────────

@router.post("/extract", summary="第一步：从自然语言提取采购记录")
async def extract_record(
    text: str,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    result = KnowledgeRecordExtract(
        needs_clarification=True,
        clarification_text="长期材料记忆目前仅支持上传供应商报价单，确认后自动保存。",
    )
    return APIResponse.ok(result.model_dump())


@router.post("/save", summary="第二步：保存确认后的记录到知识库")
async def save_record(
    data: KnowledgeSaveInput,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
) -> APIResponse:
    result = KnowledgeSaveResult(
        success=False,
        message="长期材料记忆目前仅支持供应商报价单确认后录入。",
    )
    return APIResponse.ok(result.model_dump())


# ── 会话管理 ──────────────────────────────────────────────────────────────

@router.post("/sessions", summary="创建对话会话")
async def create_session(
    data: SessionCreate,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    if data.project_id is not None:
        from sqlalchemy import select
        from app.models.project import Project
        project = (await db.execute(
            select(Project).where(
                Project.id == data.project_id,
                Project.team_id == team_id,
                Project.is_deleted.is_(False),
            )
        )).scalar_one_or_none()
        if project is None:
            from app.core.exceptions import ProjectNotFoundError
            raise ProjectNotFoundError()
    out = await KnowledgeBaseManager.create_session(current_user.user_id, data, db)
    await db.commit()
    return APIResponse.ok(out.model_dump())


@router.get("/sessions", summary="获取项目会话列表")
async def list_sessions(
    project_id: int,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """校验项目属于当前团队后返回当前用户会话。"""
    from app.services.project_service import ProjectService
    await ProjectService.get_project(project_id, team_id, db)
    sessions = await KnowledgeBaseManager.list_sessions(current_user.user_id, project_id, db)
    return APIResponse.ok([session.model_dump() for session in sessions])


@router.delete("/sessions/{session_id}", summary="删除对话会话")
async def delete_session(
    session_id: int,
    current_user: UserInfo = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    await KnowledgeBaseManager.delete_session(session_id, current_user.user_id, db)
    await db.commit()
    return APIResponse.ok()


async def _read_knowledge_content(path: str) -> str:
    """读取当前支持的知识文档格式，Excel 转为行文本。"""
    import asyncio
    from pathlib import Path
    suffix = Path(path).suffix.lower()
    raw = await local_storage.read(path)
    if suffix in {".txt", ".md"}:
        return raw.decode("utf-8", errors="replace")

    def _extract_pdf() -> str:
        from io import BytesIO
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(raw))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)

    def _extract_xlsx() -> str:
        import io
        import openpyxl
        workbook = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        rows = []
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                values = [str(value) for value in row if value is not None]
                if values:
                    rows.append("\t".join(values))
        return "\n".join(rows)

    # PDF/Excel 解析为同步 CPU 密集操作，放线程池避免阻塞事件循环
    if suffix == ".pdf":
        return await asyncio.to_thread(_extract_pdf)
    if suffix == ".xlsx":
        return await asyncio.to_thread(_extract_xlsx)
    from app.core.exceptions import UnsupportedFormatError
    raise UnsupportedFormatError(f"知识库暂不支持格式：{suffix}")


@router.get("/sessions/{session_id}/messages", summary="获取会话消息列表")
async def get_messages(
    session_id: int,
    current_user: UserInfo = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    msgs = await KnowledgeBaseManager.get_session_messages(
        session_id, current_user.user_id, db
    )
    return APIResponse.ok([m.model_dump() for m in msgs])
