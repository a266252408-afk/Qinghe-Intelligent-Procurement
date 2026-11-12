# SDD — 清单解析 Agent（list_parser_agent）

> **依据**：system-design.md §2.2.2，PRD §FR-2，tech-stack.md §5.4
> **代码位置**：`backend/app/agents/list_parser.py`
> **模型档位**：轻量档（结构化提取）

---

## 1. 功能描述

从文件（Excel/CSV）或文本输入中提取结构化采购清单（`PurchaseList`）。
使用 `with_structured_output(PurchaseList)` 直接获得 Pydantic 对象，不做二次解析。
SSE 返回给前端时展开为 `items / confidence / needs_review`，避免前端依赖内部 `purchase_list` 包装层。
置信度 < 0.8 时标记不确定字段，由前端高亮提示人工确认。
轻量模型不可用时，对标准 CSV/Excel/TXT 表头执行确定性兜底解析，保证基础清单仍可展示并进入人工核对。
不直接操作数据库，结果返回给 API 层，由用户确认后再由 `PurchaseOrderService.save_items()` 入库。

---

## 2. 接口签名

```python
from app.schemas.list_parser import ParseInput, ParseResult

class ListParserAgent:

    @staticmethod
    async def parse(
        data: ParseInput,         # 文件路径或文本内容
        session_id: str,
        db: AsyncSession,         # 仅用于 LLMCallLogger
    ) -> ParseResult:
        """解析输入为结构化采购清单。
        1. 若 file_path 不为 None：用 openpyxl/csv 读取内容转为文本
        2. 调用轻量档 LLM with_structured_output(PurchaseList)
        3. 记录 LLMCallLogger.log()
        4. 返回 ParseResult（含 items + 置信度）
        """
```

### Pydantic 模型（`backend/app/schemas/list_parser.py`）

```python
class ParseInput(BaseModel):
    file_path: str | None     # 本地存储路径（由 StorageInterface 返回）
    text: str | None          # 直接文本输入；file_path 与 text 二选一

class PurchaseItem(BaseModel):
    species: str              # 苗木品种中文名称
    spec: str                 # 规格，如"胸径12cm"
    quantity: float           # 数量
    unit: str                 # 单位，如"株"
    unit_price: float | None  # 单价，文件中有则提取
    uncertain: bool = False   # True 表示该字段不确定，前端高亮

class PurchaseList(BaseModel):
    items: list[PurchaseItem]
    confidence: float         # 整体置信度 0-1

class ParseResult(BaseModel):
    purchase_list: PurchaseList
    raw_text: str             # 传给 LLM 的原始文本（调试用）
    needs_review: bool        # 任意字段 uncertain=True 或 confidence < 0.8
```

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `LLMFactory.get_light()` | 结构化提取 |
| `LLMCallLogger.log()` | 成本记录 |
| `openpyxl` | 读取 Excel 文件 |
| `csv` (标准库) | 读取 CSV 文件 |
| `aiofiles` | 异步读取文本文件 |
| `app.core.exceptions.ParseError` | 文件读取或 LLM 解析失败 |

### Prompt 精简规范（约 80 token）

```
提取苗木清单为JSON。规则：
1. species 用中文标准名（香樟不写成樟树）
2. spec 含数值+单位（如"胸径12cm"）
3. quantity 为正数
4. uncertain=true 表示该字段不确定
{{input}}
```

---

## 4. 异常处理

| 异常 | 触发条件 | 处理策略 |
|:---- |:-------- |:-------- |
| `ParseError` | 文件格式损坏 / 内容无法读取 | 返回 HTTP 422，提示用户检查文件 |
| `LLMUnavailableError` | 轻量档 LLM 不可用 | 返回 HTTP 503 + `source:"unavailable"`，提示手动录入 |
| 空输入 | file_path 和 text 均为 None | 返回 HTTP 422 |
