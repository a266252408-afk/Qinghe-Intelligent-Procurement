"""路由 Hook：在路由结果返回后、执行意图前提供可插拔的决策点。

当前默认 Hook 处理 JEV 低置信度，把路由转成人工确认弹窗。
后续审计、告警等能力只需注册新 Hook，不修改 ChatAgent（开闭原则）。
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol
from uuid import uuid4

from app.core.config import settings
from app.schemas.router import RouteConfirmPayload, RouteOption, RouteResult

logger = logging.getLogger(__name__)


@dataclass
class RouteHookContext:
    """Hook 输入：一次路由的完整上下文。"""

    message: str
    session_id: int
    user_id: int
    team_id: int
    route: RouteResult
    has_file: bool = False
    file_type: str | None = None
    file_id: str | None = None
    file_name: str | None = None
    upload_id: int | None = None


@dataclass
class RouteHookResult:
    """Hook 输出：continue 继续执行，confirm 转人工确认。"""

    action: Literal["continue", "confirm"]
    payload: dict | None = None


class RouteHook(Protocol):
    """路由 Hook 协议。"""

    async def __call__(self, ctx: RouteHookContext) -> RouteHookResult: ...


# 6 类活跃意图的展示文案与“当前是否真正可执行”的说明
_INTENT_META: dict[str, tuple[str, str]] = {
    "parse_list": ("解析采购清单", "解析上传的采购清单/苗木表文件"),
    "parse_quote": ("解析供应商报价", "解析上传的报价单文件"),
    "generate_inquiry": ("生成询价单", "生成询价单并向供应商询价"),
    "compare": ("比价", "比较多家供应商报价并给出建议"),
    "knowledge_query": ("查询行业知识", "查询规范、养护方法等公共知识"),
    "chat": ("普通对话", "按通用对话回答，可查长期材料记录"),
}


def _executable_note(intent: str, file_type: str | None) -> tuple[bool, str | None]:
    """返回该意图在当前上下文是否可真正执行，以及需要提示的说明。"""
    if intent == "chat":
        return True, None
    if intent == "parse_list":
        if file_type == "list":
            return True, None
        return False, "需要先上传采购清单文件"
    if intent == "parse_quote":
        if file_type == "quote":
            return True, None
        return False, "需要先上传供应商报价单"
    if intent == "knowledge_query":
        return True, None
    if intent in {"generate_inquiry", "compare"}:
        return False, "当前仅提示到采购单详情页操作"
    return False, None


def _build_options(route: RouteResult, file_type: str | None) -> list[RouteOption]:
    """构造全部 6 类选项，按模型概率降序；缺失概率按 0 处理。"""
    options: list[RouteOption] = []
    ordered = sorted(
        _INTENT_META,
        # 概率相同时把模型建议意图排在最前（轻量模型降级没有 probabilities）
        key=lambda intent: (
            route.probabilities.get(intent, 0.0),
            intent == route.intent,
        ),
        reverse=True,
    )
    for intent in ordered:
        label, description = _INTENT_META[intent]
        executable, note = _executable_note(intent, file_type)
        options.append(RouteOption(
            intent=intent,  # type: ignore[arg-type]
            label=label,
            description=description,
            probability=float(route.probabilities.get(intent, 0.0)),
            executable=executable,
            note=note,
        ))
    return options


def build_confirm_payload(
    ctx: RouteHookContext,
    user_message_id: int,
) -> dict:
    """生成人工确认 payload；ChatAgent 负责补 user_message_id 后落库。"""
    now = datetime.now(timezone.utc)
    payload = RouteConfirmPayload(
        token=uuid4().hex,
        status="pending",
        message=ctx.message,
        has_file=ctx.has_file,
        file_type=ctx.file_type,
        file_id=ctx.file_id,
        file_name=ctx.file_name,
        upload_id=ctx.upload_id,
        user_message_id=user_message_id,
        jev_intent=ctx.route.intent,
        source=ctx.route.source,
        confidence=ctx.route.confidence,
        threshold=settings.JEV_LOW_CONFIDENCE_THRESHOLD,
        probabilities=ctx.route.probabilities,
        options=_build_options(ctx.route, ctx.file_type),
        created_at=now.isoformat(),
        ttl_minutes=settings.ROUTE_CONFIRM_TTL_MINUTES,
    )
    return payload.model_dump(mode="json")


class ManualConfirmationHook:
    """JEV 低置信度 → 人工确认。"""

    async def __call__(self, ctx: RouteHookContext) -> RouteHookResult:
        # JEV 与轻量模型都可能带低置信度标记；规则结果永远不触发
        if not ctx.route.needs_confirmation:
            return RouteHookResult(action="continue")
        # user_message_id 在落库后才知道；这里先返回构建器占位标记，
        # 由 ChatAgent 落库拿到 ID 后再调用 build_confirm_payload。
        return RouteHookResult(action="confirm", payload=None)


class RouteHookRegistry:
    """按注册顺序派发 Hook，首个非 continue 结果生效。"""

    def __init__(self) -> None:
        self._hooks: list[RouteHook] = []

    def register(self, hook: RouteHook) -> None:
        self._hooks.append(hook)

    async def dispatch(self, ctx: RouteHookContext) -> RouteHookResult:
        for hook in self._hooks:
            result = await hook(ctx)
            if result.action != "continue":
                return result
        return RouteHookResult(action="continue")


route_hook_registry = RouteHookRegistry()
route_hook_registry.register(ManualConfirmationHook())
