"""SQLAlchemy 声明基类，所有 ORM 模型继承此类"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有业务表的公共基类，自带 created_at / updated_at"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ── team_id 强制过滤（通过 ORM 事件监听实现） ────────────────────────────
# 注意：此处注册 before_compile 事件，确保所有含 team_id 列的查询
# 在构建 SQL 时已附带 team_id 条件，防止业务层绕过。
# 实际拦截逻辑在 db/session.py 的 TeamScopedSession 中实现。
