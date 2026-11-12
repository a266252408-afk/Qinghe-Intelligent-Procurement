"""长期材料历史记录请求与响应 Schema。"""
from datetime import date, datetime

from pydantic import BaseModel, Field


class MaterialHistoryFilter(BaseModel):
    """长期记忆筛选条件。"""

    supplier_name: str | None = Field(default=None, max_length=100)
    material_name: str | None = Field(default=None, max_length=100)
    project_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None


class MaterialHistoryOut(BaseModel):
    """长期材料历史记录展示模型。"""

    record_id: int
    supplier_name: str
    material_name: str
    spec: str
    quantity: float | None
    unit: str
    quote_price: float | None
    total_price: float | None
    final_price: float | None
    quote_date: date | None
    valid_until: date | None
    delivery_days: int | None
    payment_terms: str | None
    project_id: int | None = None
    project_name: str | None = None
    source_file: str
    uploaded_by: int | None
    uploaded_by_name: str | None
    confirmed_by: int | None
    confirmed_by_name: str | None
    created_at: datetime
    ordered_at: datetime | None
    arrived_at: datetime | None
    receipt_status: str | None

    model_config = {"from_attributes": True}
