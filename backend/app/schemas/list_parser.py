"""清单解析 Agent Pydantic Schema"""
from pydantic import BaseModel


class ParseInput(BaseModel):
    file_path: str | None = None
    text: str | None = None


class PurchaseItem(BaseModel):
    species: str
    spec: str
    quantity: float
    unit: str
    unit_price: float | None = None
    uncertain: bool = False         # True 表示前端需高亮提示确认


class PurchaseList(BaseModel):
    items: list[PurchaseItem]
    confidence: float               # 0-1


class ParseResult(BaseModel):
    purchase_list: PurchaseList
    raw_text: str = ""             # 传给 LLM 的原始文本（调试用）
    needs_review: bool             # 有不确定字段或整体置信度 < 0.8
