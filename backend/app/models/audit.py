"""审计日志 ORM 模型"""
from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    """关键操作审计日志，保留 90 天（tech-stack.md §8.5）"""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)       # create / update / delete / approve / reject
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)  # PurchaseOrder / ApprovalRecord ...
    target_id: Mapped[int] = mapped_column(nullable=False)
    diff_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # 变更前后差异
