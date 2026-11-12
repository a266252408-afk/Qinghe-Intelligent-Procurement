"""询价单与报价单 Pydantic Schema"""
from datetime import date, datetime
from pydantic import BaseModel


class QuoteItemInput(BaseModel):
    species: str
    spec: str = ""
    unit: str = ""
    unit_price: float | None = None
    final_price: float | None = None
    quantity: float | None = None
    total_price: float | None = None
    delivery_days: int | None = None
    payment_terms: str | None = None
    valid_until: date | None = None


class QuoteCreateInput(BaseModel):
    order_id: int
    supplier_name: str
    file_path: str
    original_name: str = ""
    upload_id: int | None = None
    quote_date: date | None = None
    items: list[QuoteItemInput]


class QuoteParseResult(BaseModel):
    order_id: int | None = None
    file_path: str
    original_name: str
    upload_id: int | None = None
    items: list[QuoteItemInput]


class QuoteItemOut(BaseModel):
    quote_item_id: int
    quote_id: int
    species: str
    spec: str
    unit: str
    unit_price: float | None
    final_price: float | None
    quantity: float | None
    total_price: float | None
    delivery_days: int | None
    payment_terms: str | None
    valid_until: date | None

    model_config = {"from_attributes": True}


class QuoteOut(BaseModel):
    quote_id: int
    order_id: int
    project_id: int
    project_name: str
    supplier_id: int | None
    supplier_name: str | None
    file_path: str
    original_name: str = ""
    items: list[QuoteItemOut] = []
    created_at: datetime
    quote_date: date | None = None

    model_config = {"from_attributes": True}


class InquirySheetOut(BaseModel):
    inquiry_id: int
    order_id: int
    template_id: str
    file_path: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TemplateInfo(BaseModel):
    template_id: str
    name: str
    description: str
