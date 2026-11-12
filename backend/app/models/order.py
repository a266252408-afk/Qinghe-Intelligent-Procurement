"""采购单与采购项 ORM 模型"""
from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # 状态机：draft / pending_approval(下单申请) / approved / ordered / received / settled / rejected
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    total_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["PurchaseItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    species: Mapped[str] = mapped_column(String(100), nullable=False)    # 苗木品种
    spec: Mapped[str] = mapped_column(String(100), nullable=False)       # 规格
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    total_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    supplier_quote_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("quote_items.id"), nullable=True
    )
    supplier_quote_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    final_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    order: Mapped["PurchaseOrder"] = relationship(back_populates="items")
