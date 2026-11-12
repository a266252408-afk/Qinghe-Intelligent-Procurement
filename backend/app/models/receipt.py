"""收货单与收货明细模型。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Receipt(Base):
    """一张供应商下单记录对应一张收货单。"""

    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_order_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_orders.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["ReceiptItem"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan"
    )


class ReceiptItem(Base):
    """收货材料明细，允许人工填写到货时间并逐项确认。"""

    __tablename__ = "receipt_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    receipt_id: Mapped[int] = mapped_column(
        ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_order_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_order_items.id", ondelete="SET NULL"), nullable=True
    )
    species: Mapped[str] = mapped_column(String(100), nullable=False)
    spec: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    supplier_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    final_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_received: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    receipt: Mapped[Receipt] = relationship(back_populates="items")
