"""询价单、报价单与报价项 ORM 模型"""
from datetime import date

from sqlalchemy import Date, ForeignKey, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InquirySheet(Base):
    __tablename__ = "inquiry_sheets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(String(50), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)   # 存储路径


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    parsed_data_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 原始解析结果备份
    quote_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    items: Mapped[list["QuoteItem"]] = relationship(
        back_populates="quote", cascade="all, delete-orphan"
    )


class QuoteItem(Base):
    __tablename__ = "quote_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    quote_id: Mapped[int] = mapped_column(
        ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    species: Mapped[str] = mapped_column(String(100), nullable=False)
    spec: Mapped[str] = mapped_column(String(100), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    unit_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    final_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    total_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    delivery_days: Mapped[int | None] = mapped_column(nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_until: Mapped[str | None] = mapped_column(Date, nullable=True)

    quote: Mapped["Quote"] = relationship(back_populates="items")
