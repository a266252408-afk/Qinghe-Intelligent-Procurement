"""知识库服务层 Pydantic Schema"""
from datetime import date, datetime
from pydantic import BaseModel


class PurchaseRecordCreate(BaseModel):
    team_id: int
    order_id: int
    species: str
    spec: str
    quantity: float
    unit: str
    project_name: str
    purchase_date: date


class QuoteRecordCreate(BaseModel):
    team_id: int
    order_id: int
    supplier_name: str
    species: str
    spec: str
    unit_price: float
    final_price: float | None = None
    delivery_days: int | None = None
    payment_terms: str | None = None
    quote_date: date


class SearchResult(BaseModel):
    source: str           # "industry" / "history"
    content: str
    score: float
    source_file: str | None = None  # 行业知识来源文件名


class HistorySearchResult(BaseModel):
    record_type: str      # "purchase" / "quote"
    species: str
    spec: str
    price: float | None
    supplier: str | None
    date: date | None
    score: float


class SessionCreate(BaseModel):
    project_id: int | None = None
    title: str = "新会话"


class SessionOut(BaseModel):
    session_id: int
    user_id: int
    project_id: int | None
    title: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    message_id: int
    session_id: int
    role: str
    content: str
    metadata: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
