"""管理员审批通过后生成的供应商下单记录。"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SupplierOrder(Base):
    """一张采购单对应一张已审批下单记录。"""

    __tablename__ = "supplier_orders"
    __table_args__ = (UniqueConstraint("purchase_order_id", name="uq_supplier_order_purchase_order"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ordered")
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    items: Mapped[list["SupplierOrderItem"]] = relationship(
        back_populates="supplier_order", cascade="all, delete-orphan", lazy="selectin"
    )


class SupplierOrderItem(Base):
    """下单时冻结的材料、供应商和成交价快照。"""

    __tablename__ = "supplier_order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_order_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    species: Mapped[str] = mapped_column(String(100), nullable=False)
    spec: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    supplier_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    supplier_quote_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    final_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    total_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    supplier_order: Mapped[SupplierOrder] = relationship(back_populates="items")
