"""比价 Agent Pydantic Schema"""
from pydantic import BaseModel, Field, model_validator


class CompareWeights(BaseModel):
    price: float = 0.4
    history: float = 0.3
    delivery: float = 0.2
    payment: float = 0.1

    @model_validator(mode="after")
    def _check_sum(self) -> "CompareWeights":
        total = round(self.price + self.history + self.delivery + self.payment, 6)
        if abs(total - 1.0) > 0.001:
            from app.core.exceptions import WeightSumError
            raise WeightSumError(f"权重之和为 {total}，必须等于 1.0")
        return self


class CompareInput(BaseModel):
    order_id: int
    weights: CompareWeights | None = None


class SupplierScore(BaseModel):
    supplier_name: str
    price_score: float
    history_score: float
    delivery_score: float
    payment_score: float
    total_score: float
    unit_price: float | None
    delivery_days: int | None
    payment_terms: str | None


class MaterialSupplierPrice(BaseModel):
    """同一材料规格对应的供应商单价。"""

    supplier_name: str
    unit_price: float | None


class MaterialPriceComparison(BaseModel):
    """按材料、规格和单位组织的供应商单价对比。"""

    species: str
    spec: str
    unit: str
    suppliers: list[MaterialSupplierPrice] = Field(default_factory=list)


class SupplierQuoteTotal(BaseModel):
    """供应商报价单总额。"""

    supplier_name: str
    total_price: float


class CompareResult(BaseModel):
    order_id: int
    suppliers: list[SupplierScore]
    bar_chart_option: dict = {}
    radar_chart_option: dict = {}
    ai_suggestion: str
    ai_suggestion_source: str = "ai"   # "ai" / "template"
    weights_used: CompareWeights
    material_price_comparisons: list[MaterialPriceComparison] = Field(default_factory=list)
    supplier_quote_totals: list[SupplierQuoteTotal] = Field(default_factory=list)
