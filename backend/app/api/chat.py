"""对话路由：SSE 流式输出"""
import asyncio
import json

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_team_id
from app.core.response import APIResponse
from app.schemas.auth import UserInfo
from app.schemas.chat import ChatInput

router = APIRouter()


@router.post("/upload")
async def upload_chat_file(
    file: UploadFile = File(...),
    file_type: str = "list",
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """保存对话附件，返回后续 ChatInput 使用的相对路径。"""
    from app.storage.local_storage import local_storage
    stored = await local_storage.save(file, team_id, file_type)
    result = stored.model_dump()
    if file_type == "quote":
        from app.services.quote_service import QuoteService
        upload = await QuoteService.register_upload(
            team_id, current_user.user_id, stored.path, stored.original_name, db
        )
        result["upload_id"] = upload.id
        await db.commit()
    return APIResponse.ok(result)


@router.post("", summary="发送消息（SSE 流式回复）")
async def chat(
    data: ChatInput,
    current_user: UserInfo = Depends(get_current_user),
    team_id: int = Depends(get_team_id),
) -> StreamingResponse:
    """返回 SSE 流：每帧为 `data: <json>\n\n`，最后一帧 done=true

    数据库会话由本端点自管（不通过 get_db 依赖）：SSE 客户端可能在收到
    done 帧后立刻断开，此时 uvicorn 的取消作用域会让请求内所有 await 立即
    取消，依赖注入的收尾（提交/关连接）也会被取消，导致连接永久泄漏。
    因此把"提交 + 关闭"打包为 shield 任务——外层立即取消，内层任务仍完整
    执行并把连接归还连接池。
    """
    from app.agents.chat import ChatAgent
    from app.db.session import AsyncSessionLocal

    db = AsyncSessionLocal()

    async def _finalize() -> None:
        """提交本次请求的落库结果并关闭会话（归还连接）"""
        try:
            await db.commit()
        except Exception:
            await db.rollback()
        await db.close()

    # 续跑前先校验待确认 token（归属/状态/过期）；失败走全局 AppError → 统一 JSON。
    # SSE 一旦开始就无法改状态码，因此必须在返回 StreamingResponse 之前完成校验。
    if data.pending_token:
        from app.services.route_decision import RouteDecisionService
        try:
            await RouteDecisionService.get_pending(
                data.session_id, current_user.user_id, data.pending_token, db
            )
        except Exception:
            await db.rollback()
            await db.close()
            raise
        await db.rollback()  # 释放读快照，ChatAgent 续跑时会重新读取

    async def event_generator():
        try:
            async for chunk in ChatAgent().chat_stream(data, current_user.user_id, team_id, db):
                payload = json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False)
                yield f"data: {payload}\n\n"
        finally:
            await asyncio.shield(_finalize())

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
