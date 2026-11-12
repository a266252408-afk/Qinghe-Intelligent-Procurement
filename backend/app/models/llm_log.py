"""LLM 成本可观测相关 ORM 模型（开发者运维表，无 team_id）"""
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LLMCallLog(Base):
    """LLM 调用日志（tech-stack.md §7.7，system-design.md §5）"""
    __tablename__ = "llm_call_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)    # 如 "list_parser"
    model: Mapped[str] = mapped_column(String(100), nullable=False)         # 如 "deepseek-v3"
    input_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    cost: Mapped[float] = mapped_column(nullable=False, default=0.0)        # 元
    latency_ms: Mapped[int] = mapped_column(nullable=False, default=0)      # 毫秒
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    session_id: Mapped[str] = mapped_column(String(100), nullable=False, default="")


class LLMCache(Base):
    """LLM 本地响应缓存（tech-stack.md §7.5 策略D）"""
    __tablename__ = "llm_cache"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 缓存键 = hash(model + system_prompt + user_input)
    prompt_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)             # 序列化 JSON
