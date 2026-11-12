"""长期材料历史记录与报价上传记录模型。"""
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class QuoteUpload(Base):
    """报价文件上传记录，确认报价前保存上传人和文件来源。"""

    __tablename__ = "quote_uploads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MaterialHistoryRecord(Base):
    """按材料明细保存的长期供应商报价历史。"""

    __tablename__ = "material_history_records"
    __table_args__ = (
        UniqueConstraint("team_id", "fingerprint", name="uq_material_history_team_fingerprint"),
        Index("ix_material_history_team_supplier", "team_id", "supplier_name"),
        Index("ix_material_history_team_material", "team_id", "material_name"),
        Index("ix_material_history_team_date", "team_id", "quote_date"),
        Index("ix_material_history_team_project", "team_id", "project_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    supplier_name: Mapped[str] = mapped_column(String(100), nullable=False)
    material_name: Mapped[str] = mapped_column(String(100), nullable=False)
    spec: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    quantity: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    quote_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    total_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    final_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    quote_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_days: Mapped[int | None] = mapped_column(nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file: Mapped[str] = mapped_column(String(500), nullable=False)
    source_quote_id: Mapped[int | None] = mapped_column(ForeignKey("quotes.id"), nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    receipt_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    uploaded_user: Mapped["User | None"] = relationship(foreign_keys=[uploaded_by])
    confirmed_user: Mapped["User | None"] = relationship(foreign_keys=[confirmed_by])
