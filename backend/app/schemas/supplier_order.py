"""供应商下单管理响应模型。"""
from datetime import datetime

from pydantic import BaseModel


class SupplierOrderItemOut(BaseModel):
    item_id: int
    supplier_order_id: int
    purchase_item_id: int | None
    species: str
    spec: str
    quantity: float
    unit: str
    supplier_name: str | None
    supplier_quote_price: float | None
    final_price: float | None
    total_price: float | None

    model_config = {"from_attributes": True}


class SupplierOrderOut(BaseModel):
    supplier_order_id: int
    purchase_order_id: int
    project_id: int
    project_name: str
    purchase_order_name: str | None = None
    status: str
    ordered_at: datetime
    items: list[SupplierOrderItemOut] = []

    model_config = {"from_attributes": True}
