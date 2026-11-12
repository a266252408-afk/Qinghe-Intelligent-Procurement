"""供应商 ORM 模型"""
from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    contact: Mapped[str | None] = mapped_column(String(50), nullable=True)   # 联系人
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    main_category: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 主营品类
    rating: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)     # 历史合作评分 0-5
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
