"""Router Agent Pydantic Schema"""
from typing import Literal, get_args

from pydantic import BaseModel

# 活跃意图的唯一事实来源；knowledge_record 已下线
RouteIntent = Literal[
    "parse_list",
    "parse_quote",
    "generate_inquiry",
    "compare",
    "knowledge_query",
    "chat",
]
ACTIVE_INTENTS = set(get_args(RouteIntent))


class RouterInput(BaseModel):
    message: str
    has_file: bool = False
    file_type: str | None = None    # list / quote / knowledge / None
    session_id: str = ""


class RouteOption(BaseModel):
    """人工确认弹窗中的一个意图选项。"""

    intent: RouteIntent
    label: str
    description: str
    probability: float = 0.0
    executable: bool = False
    note: str | None = None


class RouteConfirmPayload(BaseModel):
    """低置信度路由的待确认 payload，写入消息 metadata 并随 SSE 下发。"""

    token: str
    status: str = "pending"
    message: str
    has_file: bool = False
    file_type: str | None = None
    file_id: str | None = None
    file_name: str | None = None
    upload_id: int | None = None
    user_message_id: int
    # 模型建议意图；字段名保留 jev_intent 以兼容已有待确认 payload
    jev_intent: RouteIntent
    # 建议来源：jev / light_llm / light_llm_fallback
    source: str = "jev"
    confidence: float
    threshold: float
    probabilities: dict[str, float] = {}
    options: list[RouteOption]
    created_at: str
    ttl_minutes: int


class PendingRoute(BaseModel):
    """从消息 metadata 还原出的待确认路由。"""

    message_id: int
    session_id: int
    token: str
    message: str
    file_id: str | None = None
    file_type: str | None = None
    file_name: str | None = None
    upload_id: int | None = None
    user_message_id: int
    options: list[RouteOption] = []


class RouteResult(BaseModel):
    intent: RouteIntent
    target_agent: str               # 目标 Agent 类名
    extracted_params: dict = {}     # 从用户输入中提取的参数
    confidence: float = 1.0
    # JEV 返回的 6 类完整概率分布；规则/轻量模型路径为空
    probabilities: dict[str, float] = {}
    # 决策来源：jev / rule / light_llm / light_llm_fallback / manual
    source: str = "light_llm"
    # 仅 JEV 低置信度时为 True，由 ChatAgent 触发人工确认 hook
    needs_confirmation: bool = False
