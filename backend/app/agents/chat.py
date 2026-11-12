"""对话 Agent：流式回复 + 上下文压缩
依据：docs/module-sdd/chat_agent.md
"""
import asyncio
import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    RouteDecisionExpiredError,
    RouteDecisionNotFoundError,
    RouteDecisionResolvedError,
)
from app.schemas.chat import ChatChunk, ChatInput, MaterialHistoryToolInput
from app.schemas.knowledge import MessageOut
from app.services.knowledge_base import KnowledgeBaseManager

logger = logging.getLogger(__name__)

_SYSTEM = """\
你是园林工程采购助手，帮助采购员完成询价、比价、清单解析等工作。
回答简洁专业，超出采购范围的问题礼貌拒绝。
当用户询问任何材料或供应商的报价、成交价、价格、采购记录或长期记忆时，必须先调用长期材料查询工具，
再依据工具结果回答；没有这类需求时不要调用该工具。
公司或苗圃名称（如"××苗木""××园林"）通常是供应商：按材料名查不到时，改用 supplier_name 查询。
查询结果为空时，更换关键词、更换字段或放宽条件再查，最多三轮。
历史材料问题只能依据长期材料查询工具返回的结构化记录回答，禁止用行业知识或旧对话内容替代工具结果；
没有记录时明确说明未找到，不要编造价格。工具返回的记录是当前团队共享数据，只能依据记录回答。"""

_COMPRESS_PROMPT = """\
将以下多轮对话摘要为100字内的简洁上下文，保留关键信息（品种/价格/决策）：
{history}"""


class ChatAgent:
    """对话 Agent（中量档，SSE 流式输出）"""

    async def chat_stream(
        self,
        data: ChatInput,
        user_id: int,
        team_id: int,
        db: AsyncSession,
    ) -> AsyncGenerator[ChatChunk, None]:
        """流式生成回复，每个 token 产生一个 ChatChunk，最后发送 done=True"""
        from app.agents.route_hooks import (
            RouteHookContext,
            build_confirm_payload,
            route_hook_registry,
        )
        from app.agents.router import (
            RouterAgent,
            _looks_like_material_history_query,
            agent_for_intent,
        )
        from app.schemas.router import RouteResult, RouterInput
        from app.services.route_decision import RouteDecisionService

        full_reply = ""
        skip_user_save = False
        before_message_id: int | None = None
        try:
            if data.pending_token:
                # 原始 user 消息在第一轮已落库；后续任何异常都不能再保存一次
                skip_user_save = True
                pending = await RouteDecisionService.get_pending(
                    data.session_id, user_id, data.pending_token, db
                )
                await RouteDecisionService.mark_resolved(
                    pending.message_id,
                    data.forced_intent or "chat",
                    data.route_cancelled,
                    user_id,
                    db,
                )
                # 使用服务端保存的原始消息与附件，不信任客户端回传内容
                data = data.model_copy(update={
                    "message": pending.message,
                    "file_id": pending.file_id,
                    "file_type": pending.file_type,
                    "file_name": pending.file_name,
                    "upload_id": pending.upload_id,
                })
                route = RouteResult(
                    intent=data.forced_intent or "chat",
                    target_agent=agent_for_intent(data.forced_intent or "chat"),
                    confidence=1.0,
                    source="manual",
                )
                before_message_id = pending.user_message_id
            else:
                route = await RouterAgent().route(
                    RouterInput(
                        message=data.message,
                        has_file=bool(data.file_id),
                        file_type=data.file_type,
                        session_id=str(data.session_id),
                    ),
                    team_id,
                    db,
                )
                hook_ctx = RouteHookContext(
                    message=data.message,
                    session_id=data.session_id,
                    user_id=user_id,
                    team_id=team_id,
                    route=route,
                    has_file=bool(data.file_id),
                    file_type=data.file_type,
                    file_id=data.file_id,
                    file_name=data.file_name,
                    upload_id=data.upload_id,
                )
                hook_result = await route_hook_registry.dispatch(hook_ctx)
                if hook_result.action == "confirm":
                    reply = "这条消息的意图不够明确，请确认要执行的操作。"
                    saved = await self._save_exchange(
                        data, user_id, reply, db,
                        metadata_factory=lambda uid: {
                            "structured_type": "route_confirm",
                            "structured_data": build_confirm_payload(hook_ctx, uid),
                        },
                    )
                    payload = (
                        (saved.metadata or {}).get("structured_data") if saved else None
                    )
                    yield ChatChunk(
                        delta=reply, done=False, session_id=data.session_id,
                        type="route_confirm", data=payload,
                    )
                    yield ChatChunk(delta="", done=True, session_id=data.session_id)
                    return

            save_user = not skip_user_save
            if route.intent == "knowledge_query":
                from app.agents.chat_knowledge import answer_knowledge_question
                # 检索前先归还读事务，避免 SQLite/连接池被慢检索长期占用
                await asyncio.shield(self._yield_connection(db))
                answer = await answer_knowledge_question(
                    question=data.message,
                    session_id=str(data.session_id),
                    team_id=team_id,
                    db=db,
                )
                yield ChatChunk(
                    delta=answer.answer, done=False, session_id=data.session_id,
                    type="knowledge", data=answer.frame,
                )
                full_reply = answer.answer
                await asyncio.shield(self._save_exchange(
                    data, user_id, full_reply, db,
                    metadata={
                        "structured_type": "knowledge",
                        "structured_data": answer.frame,
                    },
                    save_user=save_user,
                ))
                yield ChatChunk(delta="", done=True, session_id=data.session_id)
                return
            if route.intent in {"generate_inquiry", "compare"}:
                reply = "请在采购单详情页操作：打开采购单 → 点击「生成询价单」或「对比报价」。"
                yield ChatChunk(delta=reply, done=False, session_id=data.session_id)
                full_reply = reply
                await asyncio.shield(self._save_exchange(
                    data, user_id, full_reply, db, save_user=save_user,
                ))
                yield ChatChunk(delta="", done=True, session_id=data.session_id)
                return
            if route.intent in {"parse_list", "parse_quote"}:
                expected = "list" if route.intent == "parse_list" else "quote"
                if not (data.file_id and data.file_type == expected):
                    label = "采购清单" if expected == "list" else "供应商报价单"
                    reply = f"请先上传{label}文件，再执行解析。"
                    yield ChatChunk(delta=reply, done=False, session_id=data.session_id)
                    full_reply = reply
                    await asyncio.shield(self._save_exchange(
                        data, user_id, full_reply, db, save_user=save_user,
                    ))
                    yield ChatChunk(delta="", done=True, session_id=data.session_id)
                    return
            # 意图已确定：提交读事务并归还连接，后续每步数据库操作重新借短连接，
            # 避免慢 LLM 环节长期占用连接池（SSE 事务范围缩短）。
            await asyncio.shield(self._yield_connection(db))
            if data.file_id and data.file_type == "list":
                from app.agents.list_parser import ListParserAgent
                from app.schemas.list_parser import ParseInput
                from app.core.config import settings
                from pathlib import Path
                parsed = await ListParserAgent().parse(
                    ParseInput(file_path=str(Path(settings.UPLOAD_DIR) / data.file_id)),
                    team_id,
                    str(data.session_id),
                    db,
                )
                yield ChatChunk(
                    delta="已完成清单解析，请核对结构化结果。",
                    done=False,
                    session_id=data.session_id,
                    type="list",
                    data={
                        **parsed.purchase_list.model_dump(),
                        "needs_review": parsed.needs_review,
                    },
                )
                full_reply = "已完成清单解析，请核对结构化结果。"
                await asyncio.shield(self._save_exchange(
                    data,
                    user_id,
                    full_reply,
                    db,
                    metadata={
                        "structured_type": "list",
                        "structured_data": {
                            **parsed.purchase_list.model_dump(),
                            "needs_review": parsed.needs_review,
                        },
                    },
                    save_user=save_user,
                ))
                yield ChatChunk(delta="", done=True, session_id=data.session_id)
                return
            if data.file_id and data.file_type == "quote":
                from app.agents.quote import parse_quote
                from pathlib import Path
                from app.core.config import settings

                quote_items = await asyncio.to_thread(
                    parse_quote, str(Path(settings.UPLOAD_DIR) / data.file_id)
                )
                quote_data = {
                    "file_id": data.file_id,
                    "file_name": data.file_name or Path(data.file_id).name,
                    "upload_id": data.upload_id,
                    "items": [item.model_dump(mode="json") for item in quote_items],
                }
                reply = "已完成报价单解析，请核对报价项目和供应商名称后确认保存。"
                yield ChatChunk(delta=reply, done=False, session_id=data.session_id, type="quote", data=quote_data)
                await asyncio.shield(self._save_exchange(
                    data, user_id, reply, db,
                    metadata={"structured_type": "quote", "structured_data": quote_data},
                    save_user=save_user,
                ))
                yield ChatChunk(delta="", done=True, session_id=data.session_id)
                return
            from app.services.llm_factory import LLMFactory
            message = data.message
            if data.file_id:
                message = f"{message}\n附件已上传并完成预处理：{data.file_type}"
            lc_messages = await self._build_messages(
                data.session_id, user_id, message, db,
                before_message_id=before_message_id,
            )
            llm = LLMFactory.get_medium()
            tool = None
            is_history_command = data.message.strip().lower().startswith(("/历史", "/history"))
            if _looks_like_material_history_query(data.message) or is_history_command:
                tool = self._build_material_history_tool(team_id, db)
            if tool is None:
                # 纯对话流式期间不需要数据库：归还连接，落库时再借短连接
                await asyncio.shield(self._yield_connection(db))
            async for delta in self._stream_with_optional_tool(
                llm, lc_messages, tool, session_id=str(data.session_id), db=db
            ):
                if delta:
                    full_reply += delta
                    yield ChatChunk(delta=delta, done=False, session_id=data.session_id)
        except (RouteDecisionExpiredError, RouteDecisionResolvedError, RouteDecisionNotFoundError) as exc:
            # 待确认选择异常：用户已有一条待确认记录，本轮不再落库
            yield ChatChunk(delta=exc.message, done=False, session_id=data.session_id)
            yield ChatChunk(delta="", done=True, session_id=data.session_id)
            return
        except Exception as exc:
            logger.warning("ChatAgent stream 失败：%s", exc)
            fallback = "AI 服务暂时不可用，请稍后重试。"
            yield ChatChunk(delta=fallback, done=False, session_id=data.session_id)
            full_reply = fallback

        # 先落库再发 done：客户端收到 done 可能立即断开，done 必须是最后一帧
        await asyncio.shield(self._save_exchange(
            data, user_id, full_reply, db, save_user=not skip_user_save,
        ))
        yield ChatChunk(delta="", done=True, session_id=data.session_id)

    def _build_material_history_tool(self, team_id: int, db: AsyncSession):
        """创建绑定当前团队上下文的长期材料查询工具，筛选条件由模型按 schema 决定。"""
        from datetime import date as date_type

        from langchain_core.tools import StructuredTool
        from app.schemas.material_history import MaterialHistoryFilter
        from app.services.material_history import MaterialHistoryService

        async def query_material_history(
            material_name: str | None = None,
            supplier_name: str | None = None,
            date_from: str | None = None,
            date_to: str | None = None,
        ) -> str:
            filters: dict[str, Any] = {}
            for key, raw in (("date_from", date_from), ("date_to", date_to)):
                if raw and str(raw).strip():
                    try:
                        filters[key] = date_type.fromisoformat(str(raw).strip())
                    except ValueError:
                        # 返回可自纠的错误 JSON 而非抛异常，模型可在下一轮修正参数重查
                        return json.dumps(
                            {"error": f"日期格式应为 YYYY-MM-DD，收到：{raw}"},
                            ensure_ascii=False,
                        )
            if material_name and material_name.strip():
                filters["material_name"] = material_name.strip()
            if supplier_name and supplier_name.strip():
                filters["supplier_name"] = supplier_name.strip()
            records = await MaterialHistoryService.list_records(
                MaterialHistoryFilter(**filters), team_id, db
            )
            if records:
                return json.dumps(
                    [record.model_dump(mode="json") for record in records],
                    ensure_ascii=False,
                )
            # 空结果必须携带可执行的下一步指引：把"换字段"建议放到模型决策点上，
            # 而不是依赖模型记住 system prompt（真实案例：qwen3.7-flash 拿到 []
            # 后自己猜到"可能是供应商"却不会换 supplier_name 重查）
            hint: dict[str, Any] = {"results": [], "hint": "按当前条件未查询到长期材料记录。"}
            if filters.get("material_name"):
                matched = await MaterialHistoryService.suggest_suppliers(
                    filters["material_name"], team_id, db
                )
                if matched:
                    hint["supplier_match"] = matched
                    hint["hint"] = (
                        f"材料名“{filters['material_name']}”未查到记录，"
                        f"但该关键词匹配到供应商：{'、'.join(matched)}。"
                        "请改用 supplier_name 查询这些供应商的历史报价和成交价。"
                    )
                else:
                    hint["hint"] = (
                        f"材料名“{filters['material_name']}”未查到记录。"
                        "可尝试更短关键词、改用 supplier_name（公司/苗圃名）"
                        "或放宽日期条件后重查。"
                    )
            return json.dumps(hint, ensure_ascii=False)

        return StructuredTool.from_function(
            coroutine=query_material_history,
            name="query_material_history",
            description=(
                "查询当前团队长期材料记忆中的历史报价和成交价。"
                "material_name 查材料名称（如：银杏、香樟）；supplier_name 查供应商名称"
                "（公司/苗圃名，如：××苗木、××园林）；date_from/date_to 限报价日期区间"
                "（YYYY-MM-DD）。至少提供一个条件；不要传完整问题，只传筛选字段。"
                "结果为空时换字段或换关键词重查：例如公司名查不到材料时改用 supplier_name。"
            ),
            args_schema=MaterialHistoryToolInput,
        )

    async def _stream_with_optional_tool(
        self,
        llm,
        messages: list,
        tool,
        tool_args: dict | None = None,
        session_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> AsyncGenerator[str, None]:
        """普通消息直接流式回复；历史问题执行多轮工具闭环并保留确定性降级。

        tool_args 仅作 expected_tool_args 透传（测试用）；生产路径不传，
        查询参数完全由模型按工具 schema 决定。闭环输出先缓冲再放行：
        模型查了但全部为空时，其"未找到"回答不可信，由确定性双字段降级接管
        （线上复测的真实故障模式：弱模型拿到换字段指引后仍直接放弃）。
        """
        if tool is None:
            from app.services.llm_gate import LLMGate
            async with LLMGate.acquire("medium"):
                async for text in self._astream_with_retry(llm, messages):
                    yield text
            return

        from app.agents.tool_loop import OpenAIToolLoop

        loop = OpenAIToolLoop(llm, [tool], session_id, db)
        collected: list[str] = []
        try:
            async for delta in loop.stream(
                messages,
                required_tool=tool.name,
                expected_tool_args=tool_args,
            ):
                collected.append(delta)
        except Exception as exc:
            logger.warning("长期材料记录整理模型失败，改用确定性回答：%s", exc)
            result = loop.last_results.get(tool.name)
            if result:
                yield _format_material_history_result(result)
            else:
                raise
            return

        # 放行门槛：至少一次工具查询返回了非空记录，模型的整理结果才可信
        if any(not _empty_records(value) for value in loop.last_results.values()):
            for delta in collected:
                yield delta
            return

        question = str(getattr(messages[-1], "content", "")) if messages else ""
        keyword = _extract_material_name(question)
        if not keyword:
            if collected:
                # 模型查过但关键词提取不出，无法证伪其回答，原样放行
                for delta in collected:
                    yield delta
            else:
                yield "请提供需要查询的材料名称。"
            return
        logger.warning("历史问题工具结果为空或未调用工具，走确定性双字段降级")
        yield await _deterministic_history_answer(keyword, tool)

    @staticmethod
    async def _astream_with_retry(llm, messages: list, attempts: int = 2) -> AsyncGenerator[str, None]:
        """流式调用带退避重试：仅当尚未向用户输出任何内容时才重试，
        避免部分输出后重试造成内容重复。覆盖上游 429/瞬时连接失败。"""
        for attempt in range(1, attempts + 1):
            emitted = False
            try:
                async for chunk in llm.astream(messages):
                    text = ChatAgent._message_content(chunk)
                    if text:
                        emitted = True
                    yield text
                return
            except Exception as exc:
                if emitted or attempt >= attempts:
                    raise
                logger.warning("对话流式连接建立失败，退避后重试一次：%s", exc)
                await asyncio.sleep(float(settings.LLM_RETRY_BACKOFF_S))

    @staticmethod
    def _message_content(message) -> str:
        """将 LangChain 消息或消息分片转换为可发送的文本。"""
        content = getattr(message, "content", message)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return str(content)


    async def _save_exchange(
        self,
        data: ChatInput,
        user_id: int,
        full_reply: str,
        db: AsyncSession,
        metadata: dict | None = None,
        save_user: bool = True,
        metadata_factory: Callable[[int], dict] | None = None,
    ) -> MessageOut | None:
        """保存本轮消息并记录对话模型调用。

        高并发下 SQLite 写锁升级可能瞬时 busy；此方法在 SSE 流收尾阶段执行，
        一旦抛错会打断整个流式响应，故对 database is locked 做有限退避重试。
        save_user=False 用于人工确认续跑：用户消息在第一轮已落库。
        metadata_factory 接收 user_message_id，用于生成依赖用户消息 ID 的 metadata。
        """
        from sqlalchemy.exc import OperationalError, PendingRollbackError
        import random
        import time as _time
        for attempt in range(1, 6):
            started = _time.monotonic()
            try:
                saved = await self._do_save_exchange(
                    data, user_id, full_reply, db,
                    metadata=metadata, save_user=save_user,
                    metadata_factory=metadata_factory,
                )
                # flush 后立即提交：写锁只在毫秒级窗口内持有。
                # 若等到 done 帧发出、响应收尾后才由 _finalize 提交，高负载下
                # 事件循环调度会把锁持有时间拉长到秒级，令并发落库集体饥饿。
                await db.commit()
                return saved
            except (OperationalError, PendingRollbackError) as exc:
                if attempt >= 5 or "database is locked" not in str(exc):
                    await db.rollback()
                    raise
                wait = 0.2 * (2 ** (attempt - 1)) + random.uniform(0, 0.2)
                logger.warning(
                    "对话落库写锁繁忙：第 %d 次尝试耗时 %.0fms，退避 %.0fms 重试",
                    attempt, (_time.monotonic() - started) * 1000, wait * 1000,
                )
                await db.rollback()
                await asyncio.sleep(wait)

    async def _do_save_exchange(
        self,
        data: ChatInput,
        user_id: int,
        full_reply: str,
        db: AsyncSession,
        metadata: dict | None = None,
        save_user: bool = True,
        metadata_factory: Callable[[int], dict] | None = None,
    ) -> MessageOut:
        """执行一轮消息与日志的实际落库，返回 assistant 消息。

        SQLite WAL 下"读快照事务升级写锁"会立即报 busy（不走 busy_timeout），
        因此先单独校验会话归属并提交释放读事务，再进入首条语句即为 INSERT
        的纯写事务——写锁竞争时由 busy_timeout 正常排队等待。
        """
        from app.services.llm_logger import LLMCallLogger

        # 归属校验与消息写入均归 knowledge_base service；
        # 校验后提交释放读快照，保证后续写入是事务首条语句（WAL busy 规避）
        await KnowledgeBaseManager.ensure_session_owned(data.session_id, user_id, db)
        await db.commit()

        user_message = None
        if save_user:
            user_message = await KnowledgeBaseManager.add_message(
                session_id=data.session_id, user_id=user_id, role="user",
                content=data.message, db=db,
                metadata=({"file_name": data.file_name, "file_type": data.file_type}
                          if data.file_name else None),
            )

        final_metadata = metadata
        if metadata_factory is not None and user_message is not None:
            final_metadata = metadata_factory(user_message.message_id)

        assistant = await KnowledgeBaseManager.add_message(
            session_id=data.session_id, user_id=user_id, role="assistant",
            content=full_reply, db=db, metadata=final_metadata,
        )

        await LLMCallLogger.log(
            agent_name="ChatAgent",
            model="unknown",
            input_tokens=0, output_tokens=0, cost=0.0,
            latency_ms=0, cache_hit=False,
            session_id=str(data.session_id), db=db,
        )
        return assistant

    @staticmethod
    async def _yield_connection(db: AsyncSession) -> None:
        """提交当前读事务并归还连接到连接池。

        用于 LLM 调用前释放数据库资源：提交只落库遥测日志等已写入数据，
        业务消息仍在最终 _save_exchange 后由接口层统一提交。
        提交失败不阻断对话主链路。
        """
        try:
            await db.commit()
        except Exception as exc:
            logger.warning("对话事务提前归还失败：%s", exc)
            try:
                await db.rollback()  # 清理失败状态，避免会话带着毒状态进入后续落库
            except Exception:
                pass

    async def _build_messages(
        self,
        session_id: int,
        user_id: int,
        current_message: str,
        db: AsyncSession,
        before_message_id: int | None = None,
    ) -> list:
        """拼接 LLM 输入：System → 历史（压缩）→ 当前输入。

        before_message_id 用于人工确认续跑：只取原始用户消息之前的历史，
        避免把已落库的原问题与确认提示再拼一次。
        """
        from langchain_core.messages import HumanMessage, SystemMessage
        history = await self._load_history(
            session_id, user_id, db, before_message_id=before_message_id
        )
        result = [SystemMessage(content=_SYSTEM)]
        result.extend(history)
        result.append(HumanMessage(content=current_message))
        return result

    async def _load_history(
        self,
        session_id: int,
        user_id: int,
        db: AsyncSession,
        before_message_id: int | None = None,
    ) -> list:
        """加载最近 N 轮对话；超阈值时用轻量模型压缩旧消息"""
        from langchain_core.messages import AIMessage, HumanMessage

        msgs_out = await KnowledgeBaseManager.get_session_messages(session_id, user_id, db)
        if not msgs_out:
            return []

        msgs: list[MessageOut] = msgs_out
        if before_message_id is not None:
            msgs = [m for m in msgs if m.message_id < before_message_id]
        if not msgs:
            return []
        recent_n = settings.MEMORY_RECENT_TURNS * 2  # 每轮 user+assistant 共 2 条
        threshold = int(recent_n / settings.MEMORY_COMPRESS_THRESHOLD)

        lc: list[HumanMessage | AIMessage] = []
        if len(msgs) > threshold:
            old_msgs = msgs[:-recent_n]
            recent_msgs = msgs[-recent_n:]
            compressed = await self._compress(old_msgs)
            if compressed:
                lc.append(HumanMessage(content=f"[历史摘要] {compressed}"))
                lc.append(AIMessage(content="明白，我已了解之前的对话内容。"))
        else:
            recent_msgs = msgs

        for m in recent_msgs:
            if m.role == "user":
                lc.append(HumanMessage(content=m.content))
            else:
                lc.append(AIMessage(content=m.content))
        return lc

    async def _compress(self, msgs: list) -> str:
        """用轻量模型压缩历史消息为摘要"""
        from app.services.llm_factory import LLMFactory
        from app.services.llm_gate import LLMGate
        history_text = "\n".join(f"{m.role}: {m.content}" for m in msgs)
        llm = LLMFactory.get_light()
        try:
            resp = await LLMGate.run(
                "light", lambda: llm.ainvoke(_COMPRESS_PROMPT.format(history=history_text[:3000]))
            )
            return resp.content if hasattr(resp, "content") else str(resp)
        except Exception as exc:
            logger.warning("ChatAgent 历史压缩失败：%s", exc)
            return ""


def _extract_material_name(message: str) -> str | None:
    """从历史价格问题中提取查询关键词，避免把整句问题传给查询工具。

    词表必须与 router._looks_like_material_history_query 的门控保持同步：
    门控放行的句式（含裸"成交价/报价"）这里要能提出关键词，否则降级链断链。
    """
    text = re.sub(r"^\s*(?:/历史|/history)\s*", "", message, flags=re.IGNORECASE)
    text = re.sub(r"^\s*(?:请问|请查询|查询|查一下|帮我查询|帮我查一下|我想知道)\s*", "", text)
    patterns = (
        # 句首时间词模式必须最前："上次买的桂花多少钱"若先走通用模式，
        # 会把"上次买的桂花"整串当作关键词
        r"^(?:上次|之前|以前|最近|上个月|上月)(?:买|采购)?[过的]?(.+?)(?:的)?(?:成交价|价格|报价|多少钱)",
        r"^(.+?)(?:的)?(?:历史成交价|历史价格|历史报价|历史价|成交记录|采购历史|采购记录|成交价|报价|多少钱)",
        r"^(.+?)(?:上次|之前|以前)(?:买|采购|报价)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            material = re.sub(r"[，。！？?：:、\s]+$", "", match.group(1))
            # 剥离句首时间词，避免"上个月桂花"整串当作关键词查询
            material = re.sub(r"^(?:最近|上周|上个月|上月|之前|以前|去年|今年)", "", material)
            return material or None
    if text and message.strip().lower().startswith(("/历史", "/history")):
        return re.sub(r"[，。！？?：:、\s]+$", "", text) or None
    return None


def _empty_records(raw_result: str) -> bool:
    """判断工具返回是否为空记录（含带指引的空结果对象；错误 JSON 视为非空）。"""
    try:
        data = json.loads(raw_result)
    except (TypeError, json.JSONDecodeError):
        return False
    if isinstance(data, dict):
        return data.get("results") == []
    return isinstance(data, list) and not data


async def _deterministic_history_answer(keyword: str, tool) -> str:
    """确定性双字段降级：先按材料名查，查空换供应商名查，返回格式化回答。

    "××苗木"这类公司名是供应商的典型形态；两级都空时返回工具的指引文本。
    """
    result = await tool.ainvoke({"material_name": keyword})
    if _empty_records(result):
        supplier_result = await tool.ainvoke({"supplier_name": keyword})
        if not _empty_records(supplier_result):
            result = supplier_result
    return _format_material_history_result(result)


def _format_material_history_result(raw_result: str) -> str:
    """将长期材料查询结果格式化为不依赖模型的可读回答。"""
    try:
        data = json.loads(raw_result)
    except (TypeError, json.JSONDecodeError):
        return raw_result
    if isinstance(data, dict):
        # 带指引的空结果对象：降级链直接展示指引文本
        return data.get("hint") or "未找到该材料的长期报价或成交记录。"
    records = data
    if not records:
        return "未找到该材料的长期报价或成交记录。"
    lines = ["已查询到长期材料记录："]
    for record in records:
        quote = record.get("quote_price")
        final = record.get("final_price")
        price = f"报价 {quote}" if quote is not None else "报价未记录"
        if final is not None:
            price += f"，成交价 {final}"
        lines.append(
            f"- 供应商：{record.get('supplier_name') or '未记录'}；"
            f"规格：{record.get('spec') or '未记录'}；{price}"
            f"；日期：{record.get('quote_date') or '未记录'}"
        )
    return "\n".join(lines)
