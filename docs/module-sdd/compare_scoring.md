# SDD — 比价评分（compare_scoring）

> **代码位置**：`backend/app/services/compare_scoring.py`
> **定位**：纯函数模块，无数据库、无大模型，供 CompareAgent 与测试共用。

---

## 1. 功能描述

用确定性代码完成报价的数值计算，避免把可计算的评分交给大模型：

- 多维度评分：价格（越低越高）、历史评级、交期（越短越高）、付款条件；
- 按"材料 + 规格 + 单位"汇总各供应商单价；
- 汇总供应商报价总额（缺失行总价时用数量 × 单价补算）；
- 生成前端柱状图与雷达图配置。

历史评级当前无数据来源，统一记 0.5；后续接入供应商履约数据时在此扩展。

---

## 2. 接口签名

```python
def calc_scores(quotes: list, weights: CompareWeights) -> list[SupplierScore]:
    """按权重计算供应商综合评分，按总分降序返回。"""

def build_material_price_comparisons(quotes: list) -> list[MaterialPriceComparison]:
    """按材料、规格和单位汇总各供应商报价单价。"""

def build_supplier_quote_totals(quotes: list) -> list[SupplierQuoteTotal]:
    """汇总供应商报价总额，缺少行总价时用数量乘单价补算。"""

def normalize_inv(val: float, lo: float | None, hi: float | None) -> float:
    """反向归一化：值越小分越高；区间缺失或相等时返回 0.5。"""

def payment_to_score(terms: str | None) -> float:
    """付款条件评分：现款/预付=0.3，到货/到付=0.7，月结/账期=1.0，其它=0.5。"""

def bar_chart(scores: list[SupplierScore]) -> dict: ...
def radar_chart(scores: list[SupplierScore], weights: CompareWeights) -> dict: ...
```

### 计算规则

- 供应商单元价取其所有报价行单价的平均值；
- 价格、交期使用反向归一化到 `[0, 1]`；
- 交期缺失时记 0.5，不参与最大/最小交期的统计；
- 综合分 = Σ(维度分 × 对应权重)，结果保留 4 位小数；
- 材料对比键会统一全角字符、空白，并把 `×`、`*`、`＊` 归一为 `x`。

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `app.schemas.compare` | `CompareWeights` / `SupplierScore` / `MaterialPriceComparison` / `SupplierQuoteTotal` |
| 标准库 `re`、`unicodedata`、`collections` | 文本归一化与分组 |

ORM 对象以鸭子类型读取（`quote.supplier_name`、`item.unit_price` 等），不直接依赖数据库会话。

---

## 4. 异常处理

- 无任何有效报价（全部缺单价）：`calc_scores` 返回空列表；
- 报价行缺单价：跳过该行参与价格均值；
- 交期缺失：该供应商交期得 0.5 分；
- 缺 `total_price`：用 `quantity × unit_price` 补算，两者都缺时按 0 计；
- 本模块为纯函数，不捕获异常；输入结构由调用方与 Pydantic 模型保证。
