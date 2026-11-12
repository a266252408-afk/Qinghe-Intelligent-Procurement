# SDD — 比价分析 Agent（compare_agent）

> **依据**：system-design.md §2.2.4，PRD §FR-5，tech-stack.md §7.2
> **代码位置**：`backend/app/agents/compare.py`
> **模型档位**：重量档（多维度推理）

---

## 1. 功能描述

对指定采购单的所有报价进行多维度对比，生成可视化数据 + AI 自然语言建议。
比价数值计算（权重打分）用确定性代码实现，不调用大模型。
大模型仅用于生成自然语言建议文本，输入为打分结果摘要。

### 比价维度与权重（默认，主管可调）

| 维度 | 默认权重 |
|:---- |:-------- |
| 单价 | 40% |
| 历史合作评分 | 30% |
| 交货期 | 20% |
| 付款条件 | 10% |

---

## 2. 接口签名

```python
from app.schemas.compare import CompareInput, CompareResult

class CompareAgent:

    @staticmethod
    async def compare(
        data: CompareInput,       # 采购单 ID + 可选自定义权重
        team_id: int,
        db: AsyncSession,
    ) -> CompareResult:
        """生成比价报告。
        1. 获取该采购单所有报价（QuoteService）
        2. 获取供应商历史评分（KnowledgeBaseManager.search_history）
        3. 确定性代码计算加权综合得分
        4. 生成 ECharts 柱状图 + 雷达图配置（option JSON）
        5. 调用重量档 LLM 生成自然语言建议（~200 token 输出）
        6. 记录 LLMCallLogger.log()
        7. 返回 CompareResult
        """
```

### Pydantic 模型（`backend/app/schemas/compare.py`）

```python
class CompareWeights(BaseModel):
    price: float = 0.4         # 单价权重
    history: float = 0.3       # 历史评分权重
    delivery: float = 0.2      # 交货期权重
    payment: float = 0.1       # 付款条件权重
    # 约束：sum == 1.0（Pydantic validator 校验）

class CompareInput(BaseModel):
    order_id: int
    weights: CompareWeights | None  # None 时用团队默认权重或全局默认

class SupplierScore(BaseModel):
    supplier_name: str
    price_score: float             # 0-100
    history_score: float           # 0-100
    delivery_score: float          # 0-100
    payment_score: float           # 0-100
    total_score: float             # 加权综合得分
    unit_price: float | None       # 报价单价（最低品种均价）
    delivery_days: int | None
    payment_terms: str | None

class CompareResult(BaseModel):
    order_id: int
    suppliers: list[SupplierScore]  # 所有供应商得分，按 total_score 降序
    bar_chart_option: dict          # ECharts 柱状图配置（价格对比）
    radar_chart_option: dict        # ECharts 雷达图配置（多维评分）
    ai_suggestion: str              # AI 自然语言建议
    ai_suggestion_source: str       # "ai" / "template"（降级时为 template）
    weights_used: CompareWeights    # 实际使用的权重
    material_price_comparisons: list[MaterialPriceComparison]
    supplier_quote_totals: list[SupplierQuoteTotal]
```

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `LLMFactory.get_heavy()` | 生成建议文本 |
| `LLMCallLogger.log()` | 成本记录 |
| `PurchaseOrderService.get_order()` | 获取采购单 |
| `KnowledgeBaseManager.search_history()` | 获取历史评分 |
| `app.models.quote.Quote` / `QuoteItem` | 查询所有报价 |

### Prompt 精简规范（约 120 token）

```
你是采购比价顾问。根据以下评分结果给出建议（100字以内）：
{{scores_summary}}
要求：明确说"建议选X供应商，理由：..."，不超过2条理由。
```

---

## 4. 异常处理

| 异常 | 触发条件 | 处理策略 |
|:---- |:-------- |:-------- |
| `OrderNotFoundError` | 采购单不存在 | HTTP 404 |
| `NoQuoteError` | 该采购单无报价可比 | HTTP 422，提示上传报价文件 |
| `LLMUnavailableError` | 重量档 LLM 不可用 | 仍返回表格+图表，`ai_suggestion_source="template"`，建议文本为固定模板 |
| `WeightSumError` | 自定义权重之和不等于 1.0 | HTTP 422 |
