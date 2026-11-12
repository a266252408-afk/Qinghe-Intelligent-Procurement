"""路由 Agent：JEV 主路由，规则 + 轻量模型作为故障降级
依据：docs/module-sdd/router_agent.md
"""
import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import LLMUnavailableError
from app.schemas.router import RouteResult, RouterInput

logger = logging.getLogger(__name__)

# 规则层：仅在 JEV 不可用时启用（附件 → 斜杠命令 → 历史关键词）
_FILE_TYPE_INTENT: dict[str, str] = {
    "list":  "parse_list",
    "quote": "parse_quote",
}
_FILE_TYPE_AGENT: dict[str, str] = {
    "list":  "ListParserAgent",
    "quote": "QuoteParseAgent",
}

_COMMAND_ROUTES: dict[str, tuple[str, str]] = {
    "/询价": ("generate_inquiry", "InquiryAgent"),
    "/比价": ("compare", "CompareAgent"),
    "/历史": ("chat", "ChatAgent"),
    "/history": ("chat", "ChatAgent"),
    "/知识": ("knowledge_query", "KnowledgeAgent"),
}

_AGENT_MAP: dict[str, str] = {
    "parse_list":        "ListParserAgent",
    "parse_quote":       "QuoteParseAgent",
    "generate_inquiry":  "InquiryAgent",
    "compare":           "CompareAgent",
    "knowledge_query":   "KnowledgeAgent",
    "chat":              "ChatAgent",
}

# JEV 与轻量模型共用的“两类问题”区分口径
_QUERY_SCOPE_GUIDE = """\

【长期材料记忆 vs 行业知识库】
- chat（长期材料记忆）：问本团队自己的历史成交价、历史报价、采购记录、
  供应商报价记录、某材料我们买过/上次买/以前报价、长期记忆。
  例：香樟上次买多少钱、银杏历史成交价、我们以前从示例苗木买过香樟吗、
      供应商报价记录、这条采购记录。
- knowledge_query（行业知识库）：问公开的行业规范、验收标准、养护方法、
  病虫害防治、修剪/施肥/浇水/移栽、成活率、种植密度、土壤等通用知识，
  不涉及本团队具体交易记录。
  例：香樟树苗怎么养护、园林绿化验收规范、香樟病虫害怎么防治、
      苗木成活率标准。

判断要点：
1. 先看用户问的是“我们自己的记录”还是“行业通用做法”，不要只看材料名。
2. 出现“我们/上次/买过/成交价/采购记录/供应商报价记录”优先 chat。
3. 出现“规范/标准/怎么养护/病虫害/修剪/施肥/浇水/移栽/成活率”优先 knowledge_query。
4. 两类信号同时出现时，看用户主要想要哪一类；无法判断时 confidence 给 0.6 以下。
5. 不要因为出现“价格”就判 chat，也不要因为出现“香樟/银杏”就判 knowledge_query。
"""

_SYSTEM_PROMPT = """\
你是园林工程采购系统的路由器，只需判断用户消息属于哪种意图。
意图枚举（6类）：
1. parse_list         - 解析/导入采购清单
2. parse_quote        - 解析/导入报价单
3. generate_inquiry   - 生成询价单
4. compare            - 比价/比较报价
5. knowledge_query    - 查询行业知识库中的公共知识
6. chat               - 通用对话 / 本团队历史材料记录查询
""" + _QUERY_SCOPE_GUIDE + """\
confidence 表示你对意图的确定程度（0-1），不确定时给 0.6 以下。
仅返回 JSON，格式：{format_instructions}"""

# JEV state 中提供给模型的命令语义（只作为上下文，不参与本地判断）
_KNOWN_COMMANDS: dict[str, str] = {
    "/询价": "generate_inquiry",
    "/比价": "compare",
    "/历史": "chat",
    "/history": "chat",
    "/知识": "knowledge_query",
}

# 问题 ID 不会发送给模型，全部判定规则必须写进 instructions
_JEV_INSTRUCTIONS = """\
你是园林工程采购系统的意图路由器。state 中包含用户消息（user_message）、
附件信息（has_file / file_type）和系统支持的斜杠命令（known_commands）。
请判断用户真正想完成的任务，从 6 个意图中选择 1 个。

意图定义：
- parse_list：解析、导入、识别采购清单/苗木表/材料表的内容。
- parse_quote：解析、导入、识别供应商报价单/报价表的内容。
- generate_inquiry：生成、制作询价单，或向供应商发起询价。
- compare：比较多家供应商的报价、比价、选最低价。
- knowledge_query：查询行业规范、验收标准、养护方法等公共知识，
  不查本团队的具体交易记录。
- chat：普通对话，包括本团队历史成交价、历史报价、采购记录查询，
  以及超范围问题。

判定要点：
1. 消息以 known_commands 中的命令开头时，按该命令对应的意图判断；
   命令之后可能还有其他文字，不要被后续文字带偏。
2. 只有明确要求“解析某个文件的内容”才选 parse_list / parse_quote；
   只是提到清单或报价单、但意图是生成或比较时，不要选解析类。
3. state 中 has_file=true 且 file_type=list/quote 时，优先选择对应的解析意图。
4. 信息不足、语义模糊或超出采购范围时选 chat，不要臆测。
""" + _QUERY_SCOPE_GUIDE

_JEV_CRITERIA: dict[str, str] = {
    "parse_list": "解析或导入采购清单、苗木表、材料表",
    "parse_quote": "解析或导入供应商报价单、报价表",
    "generate_inquiry": "生成询价单，向供应商发起询价",
    "compare": "比较多家供应商报价、比价",
    "knowledge_query": "查询行业规范、验收标准、养护方法等公共知识（不查本团队交易记录）",
    "chat": "闲聊、本团队历史成交价/报价/采购记录查询、其他情况",
}


class RouterAgent:
    """意图路由 Agent：JEV 主路由，规则 + 轻量模型故障降级。"""

    async def route(
        self,
        data: RouterInput,
        team_id: int,
        db: AsyncSession,
    ) -> RouteResult:
        """JEV 优先；低置信度或调用失败时降级规则 + 轻量模型，仍不确定才转人工。"""
        if self._jev_available():
            try:
                result = await self._jev_route(data, team_id, db)
                if result.confidence >= settings.JEV_LOW_CONFIDENCE_THRESHOLD:
                    return result
                logger.info(
                    "JEV 低置信度 %.2f（%s），进入规则+轻量模型降级",
                    result.confidence, result.intent,
                )
            except Exception as exc:
                logger.warning("JEV 路由失败，降级规则+轻量模型：%s", exc)
        return await self._fallback_route(data, team_id, db)

    @staticmethod
    def _jev_available() -> bool:
        """未配置 Key 时视为停用，保证测试/CI 不联网。"""
        return bool(settings.JEV_ENABLED and settings.jev_api_key)

    async def _jev_route(
        self,
        data: RouterInput,
        team_id: int,
        db: AsyncSession,
    ) -> RouteResult:
        """调用 JEV 做意图分类，并把置信度、概率分布写入 RouteResult。"""
        from app.services.llm_factory import LLMFactory
        from app.services.llm_gate import LLMGate
        from app.services.llm_logger import LLMCallLogger

        state = {
            "user_message": data.message,
            "has_file": data.has_file,
            "file_type": data.file_type,
            "known_commands": _KNOWN_COMMANDS,
            "channel": "园林工程采购助手 · 对话入口",
        }
        questions = {
            "intent": {
                "type": "choice",
                "instructions": _JEV_INSTRUCTIONS,
                "criteria": _JEV_CRITERIA,
            }
        }

        started = time.monotonic()
        try:
            payload: dict[str, Any] = await LLMGate.run(
                "jev", lambda: LLMFactory.get_jev().judge(state, questions)
            )
        except Exception as exc:
            await self._log_jev_call(
                db, data, model=settings.JEV_MODEL, latency_ms=self._elapsed_ms(started),
                usage={}, failed=True,
            )
            raise exc

        latency_ms = self._elapsed_ms(started)
        result = self._parse_jev_payload(payload)
        await self._log_jev_call(
            db, data, model=str(payload.get("model") or settings.JEV_MODEL),
            latency_ms=latency_ms, usage=payload.get("usage") or {},
        )
        return result

    @staticmethod
    def _parse_jev_payload(payload: dict[str, Any]) -> RouteResult:
        """校验 JEV 响应并转换为 RouteResult。"""
        answer = (payload.get("answers") or {}).get("intent") or {}
        intent = answer.get("choice")
        if intent not in _AGENT_MAP:
            raise LLMUnavailableError(f"JEV 返回未知意图：{intent!r}")

        probabilities = {
            str(key): float(value)
            for key, value in (answer.get("probabilities") or {}).items()
        }
        return RouteResult(
            intent=intent,
            target_agent=_AGENT_MAP[intent],
            confidence=float(answer.get("confidence") or 0.0),
            probabilities=probabilities,
            source="jev",
        )

    @staticmethod
    async def _log_jev_call(
        db: AsyncSession,
        data: RouterInput,
        model: str,
        latency_ms: int,
        usage: dict[str, Any],
        failed: bool = False,
    ) -> None:
        """记录 JEV 调用；失败也记一条 0 token 日志便于观测故障。"""
        from app.services.llm_logger import LLMCallLogger

        await LLMCallLogger.log(
            agent_name="RouterAgent.jev_error" if failed else "RouterAgent.jev",
            model=model,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            cost=0.0,  # JEV 无公开计价，成本暂记 0
            latency_ms=latency_ms,
            cache_hit=False,
            session_id=data.session_id,
            db=db,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.monotonic() - started) * 1000)

    async def _fallback_route(
        self,
        data: RouterInput,
        team_id: int,
        db: AsyncSession,
    ) -> RouteResult:
        """JEV 故障降级：先规则，再轻量模型。"""
        rule_result = self._rule_route(data)
        if rule_result is not None:
            return rule_result
        return await self._llm_route(data, team_id, db)

    @staticmethod
    def _rule_route(data: RouterInput) -> RouteResult | None:
        """复刻原有确定性规则，仅用于 JEV 故障降级。"""
        if data.has_file and data.file_type in _FILE_TYPE_INTENT:
            intent = _FILE_TYPE_INTENT[data.file_type]
            return RouteResult(
                intent=intent,
                target_agent=_FILE_TYPE_AGENT[data.file_type],
                confidence=1.0,
                source="rule",
            )

        for command, (intent, agent) in _COMMAND_ROUTES.items():
            if data.message.strip().startswith(command):
                return RouteResult(
                    intent=intent,
                    target_agent=agent,
                    confidence=1.0,
                    source="rule",
                )

        if _looks_like_material_history_query(data.message):
            return RouteResult(
                intent="chat",
                target_agent="ChatAgent",
                confidence=1.0,
                source="rule",
            )
        return None

    async def _llm_route(
        self,
        data: RouterInput,
        team_id: int,
        db: AsyncSession,
    ) -> RouteResult:
        """调用轻量 LLM 进行意图分类（JEV 故障时的最后一道降级）。"""
        from langchain.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import PydanticOutputParser
        from app.services.llm_factory import LLMFactory
        from app.services.llm_logger import LLMCallLogger

        parser = PydanticOutputParser(pydantic_object=RouteResult)
        prompt = ChatPromptTemplate.from_messages([
            ("system", _SYSTEM_PROMPT),
            ("human", "{message}"),
        ]).partial(format_instructions=parser.get_format_instructions())

        llm = LLMFactory.get_light()
        chain = prompt | llm | parser

        t0 = time.monotonic()
        failed = False
        try:
            from app.services.llm_gate import LLMGate
            result: RouteResult = await LLMGate.run(
                "light", lambda: chain.ainvoke({"message": data.message})
            )
        except Exception as exc:
            logger.warning("RouterAgent LLM 失败，降级为 chat：%s", exc)
            failed = True
            result = RouteResult(
                intent="chat", target_agent="ChatAgent",
                confidence=0.5, source="light_llm_fallback",
                needs_confirmation=True,
            )

        latency_ms = int((time.monotonic() - t0) * 1000)
        await LLMCallLogger.log(
            agent_name="RouterAgent",
            model=LLMFactory.get_light().model_name,  # type: ignore[attr-defined]
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            latency_ms=latency_ms,
            cache_hit=False,
            session_id=data.session_id,
            db=db,
        )

        if not failed:
            result.source = "light_llm"
            result.target_agent = _AGENT_MAP.get(result.intent, "ChatAgent")
            result.probabilities = {}
            result.confidence = max(0.0, min(1.0, float(result.confidence)))
            result.needs_confirmation = (
                result.confidence < settings.JEV_LOW_CONFIDENCE_THRESHOLD
            )
        return result


def agent_for_intent(intent: str) -> str:
    """意图 → 目标 Agent 类名；未知意图兜底 ChatAgent。"""
    return _AGENT_MAP.get(intent, "ChatAgent")


def _looks_like_material_history_query(message: str) -> bool:
    """识别需要交给 ChatAgent 长期材料工具的明显历史价格问题。"""
    terms = (
        "历史成交价",
        "历史价格",
        "历史报价",
        "历史价",
        "成交记录",
        "成交价",
        "采购历史",
        "采购记录",
        "长期记忆",
        "买过",
        "采购过",
        "上次",
        "上个月",
        "上月",
        "上周",
        "之前买",
        "以前买",
        "以前报价",
    )
    return any(term in message for term in terms)
