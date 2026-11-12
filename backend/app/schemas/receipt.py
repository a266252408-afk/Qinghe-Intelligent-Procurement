"""收货管理请求与响应模型。"""
from datetime import datetime

from pydantic import BaseModel


class ReceiptItemUpdate(BaseModel):
    item_id: int
    arrived_at: datetime | None = None
    is_received: bool = False


class ReceiptUpdate(BaseModel):
    items: list[ReceiptItemUpdate]


class ReceiptItemOut(BaseModel):
    item_id: int
    receipt_id: int
    supplier_order_item_id: int | None
    species: str
    spec: str
    quantity: float
    unit: str
    supplier_name: str | None
    final_price: float | None
    arrived_at: datetime | None
    is_received: bool

    model_config = {"from_attributes": True}


class ReceiptOut(BaseModel):
    receipt_id: int
    supplier_order_id: int
    project_id: int
    project_name: str
    status: str
    confirmed_at: datetime | None
    items: list[ReceiptItemOut] = []

    model_config = {"from_attributes": True}
