"""采购单相关 Pydantic Schema"""
from datetime import datetime
from pydantic import BaseModel, Field


class OrderItemCreate(BaseModel):
    species: str
    spec: str = ""
    quantity: float = Field(gt=0, description="采购数量，必须大于 0")
    unit: str
    unit_price: float | None = None
    total_price: float | None = None
    supplier_name: str | None = None
    supplier_quote_item_id: int | None = None
    supplier_quote_price: float | None = None
    final_price: float | None = None


class OrderItemOut(BaseModel):
    item_id: int
    order_id: int
    species: str
    spec: str
    quantity: float
    unit: str
    unit_price: float | None
    total_price: float | None
    supplier_name: str | None
    supplier_quote_item_id: int | None
    supplier_quote_price: float | None
    final_price: float | None

    model_config = {"from_attributes": True}


class OrderCreate(BaseModel):
    project_id: int
    name: str | None = Field(default=None, max_length=120)
    remark: str | None = None


class OrderUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    remark: str | None = None


class OrderOut(BaseModel):
    order_id: int
    project_id: int
    project_name: str
    name: str | None
    creator_id: int
    status: str
    total_amount: float | None
    remark: str | None
    items: list[OrderItemOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrderListOut(BaseModel):
    total: int
    items: list[OrderOut]


class SupplierOption(BaseModel):
    """采购项可选择的供应商报价。"""

    quote_id: int
    quote_item_id: int
    supplier_name: str
    unit_price: float | None


class OrderSupplierOptionsOut(BaseModel):
    """采购单各材料对应的供应商报价选项。"""

    item_id: int
    species: str
    spec: str
    unit: str
    suppliers: list[SupplierOption]
