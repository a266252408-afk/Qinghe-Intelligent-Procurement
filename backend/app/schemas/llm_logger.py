"""LLM 日志服务 Pydantic Schema"""
from pydantic import BaseModel


class LLMCallLogCreate(BaseModel):
    agent_name: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    latency_ms: int
    cache_hit: bool
    session_id: str = ""


class LLMCallSummary(BaseModel):
    key: str               # model 名称或 agent_name
    total_calls: int
    total_cost: float
    avg_latency_ms: float
