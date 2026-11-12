# SDD — 报价单解析 Agent（quote_agent）

> **代码位置**：`backend/app/agents/quote.py`
> **定位**：把供应商报价文件解析为待人工确认的结构化报价项。
> **约束**：确定性解析，不调用大模型；解析结果必须经用户确认后才入库。

---

## 1. 功能描述

读取供应商提供的报价文件（xlsx / csv / txt），按表头别名识别列，输出 `QuoteItemInput` 列表，
供前端展示并由用户确认。解析只做格式与字段映射，不做价格合理性判断。

支持能力：

- 编码兼容：`utf-8-sig`（带 BOM）→ `gbk` → `utf-8(replace)` 依次尝试；
- 分隔符：文本中存在 tab 时按 tab 切分，否则按逗号，避免千分位逗号被误切；
- 表头别名：品种/规格/数量/单位/单价/总价/交货期/付款条件/有效期；
- 跳过空行与"合计/总计/小计"行；缺单价的行不进入结果；
- 日期规范化：斜杠、点统一为连字符并补零，便于 Pydantic 解析为 `date`。

---

## 2. 接口签名

```python
def parse_quote(file_path: str) -> list[QuoteItemInput]:
    """解析供应商报价表，返回用户确认前的报价项。"""

def _decode_bytes(data: bytes) -> str: ...
def _read_text(file_path: str) -> str: ...
def _number(value: str | None) -> float | None: ...
def _date(value: str) -> str | None: ...
```

### 输出模型

`QuoteItemInput`（`app.schemas.quote`）字段：

| 字段 | 说明 |
|:---- |:---- |
| `species` | 品种（必填列） |
| `spec` | 规格 |
| `unit` | 单位 |
| `quantity` | 数量 |
| `unit_price` | 含税单价（必填列） |
| `total_price` | 行总价 |
| `delivery_days` | 交货天数，缺失为 `None` |
| `payment_terms` | 付款条件 |
| `valid_until` | 报价有效期（规范化日期） |

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `openpyxl` | 读取 xlsx（只读、取计算值） |
| 标准库 `csv` / `io` / `re` / `pathlib` | 文本解析与日期规范化 |
| `app.schemas.quote.QuoteItemInput` | 输出结构 |
| `app.core.exceptions.ParseError` | 统一解析异常 |

---

## 4. 异常处理

| 场景 | 处理 |
|:---- |:---- |
| 文件不存在 | `ParseError("报价文件不存在")` |
| 不支持的扩展名 | `ParseError("报价单仅支持 xlsx、csv、txt 文件")` |
| 文件为空 / 无表头 | `ParseError("报价单为空")` |
| 缺品种列或缺单价列 | `ParseError("报价单缺少品种或单价列")` |
| 无有效明细行 | `ParseError("未识别到有效报价项目")` |
| 单元格无法转数字 | 该字段记 `None`；缺单价的行整行跳过 |
| 编码无法识别 | 最终以 `utf-8(errors="replace")` 读取，不中断 |

API 层把 `ParseError` 转成统一响应格式；解析结果始终需要用户确认后才写入报价与长期历史。
