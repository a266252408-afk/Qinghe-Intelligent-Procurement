# SDD — 询价单生成 Agent（inquiry_agent）

> **依据**：system-design.md §2.2.3，PRD §FR-3
> **代码位置**：`backend/app/agents/inquiry.py`
> **模型档位**：轻量档（模板填充，非生成）

---

## 1. 功能描述

基于采购单中的采购清单，填充询价单 Excel 模板并生成可下载文件。询价单生成不依赖采购单审批状态，只要采购单存在采购项即可生成。
支持 4 个预设模板（标准/简版/含交货期要求版/绿化工程量清单版）。
生成成功后自动触发长期记忆库记录（调用 `KnowledgeBaseManager.save_purchase_record()`）。
大模型仅用于填充模板中的自然语言备注字段（少量），主体逻辑为确定性代码。

---

## 2. 接口签名

```python
from app.schemas.inquiry import InquiryGenerateInput, InquiryResult

class InquiryAgent:

    @staticmethod
    async def generate(
        data: InquiryGenerateInput,    # 采购单 ID + 模板 ID
        team_id: int,
        session_id: str,
        db: AsyncSession,
    ) -> InquiryResult:
        """生成询价单文件。
        1. 通过 PurchaseOrderService.get_order_with_project_scoped() 获取采购清单与所属项目名称
        2. 加载 Excel 模板（标准模板内存构建；绿化清单模板读取 backend/app/templates/）
        3. 用 openpyxl 填充品名/规格/数量/单位
        4. 若模板含备注字段 → 调用轻量档 LLM 生成简短备注（可选）
        5. 保存文件到团队上传目录
        6. 写入 inquiry_sheets 表
        7. 调用 KnowledgeBaseManager.save_purchase_record()
        8. 记录 LLMCallLogger.log()（若调用了 LLM）
        """

    @staticmethod
    def list_templates() -> list[TemplateInfo]:
        """返回可用模板列表（从本地 templates 目录读取）。"""
```

### Pydantic 模型（`backend/app/schemas/inquiry.py`）

```python
class InquiryGenerateInput(BaseModel):
    order_id: int             # 采购单 ID
    template_id: str          # "standard" / "simple" / "with_delivery" / "greening_boq"

class TemplateInfo(BaseModel):
    template_id: str
    name: str                 # 模板显示名称
    description: str          # 模板说明

class InquiryResult(BaseModel):
    inquiry_id: int           # 写入数据库的询价单 ID
    file_path: str            # 存储路径（供下载）
    filename: str             # 下载文件名
    preview_items: list[dict] # 预览数据（品名/规格/数量/单位）
    template_id: str
    template_name: str        # 模板显示名称
    download_url: str         # 询价单下载接口地址
```

### 模板清单

| template_id | 显示名称 | 说明 |
|:---- |:---- |:---- |
| `standard` | 标准询价单 | 品名/规格/数量/单位/单价/备注 |
| `simple` | 简化询价单 | 仅品名/数量/单位 |
| `with_delivery` | 含交期询价单 | 标准列 + 交货天数/付款条件 |
| `greening_boq` | 绿化工程量清单 | 参照花箱绿化工程量清单版式，含规格/工程量/综合单价/综合合价/合计 |

### 绿化工程量清单模板（greening_boq）

底版文件：`backend/app/templates/greening_boq.xlsx`（由业务提供的《花箱绿化工程量清单》原表保存）。

版式与样式规则（必须与原表一致）：
- 第 1 行为标题（`A1:L1` 合并），第 2-5 行为合并表头（`A2:A5` … `L2:L5`），明细从第 6 行开始。
- `B2` 写入 `项目名称（{所属项目名称}）`，项目名称取采购单关联的 `Project.name`，不是采购单自定义名称。
- 明细列映射：`B=品种`、`F=采购单规格原文`、`G=单位`、`I=数量`、`J=综合单价（采购单已有单价时带入）`；原表无对应数据的 `A/C/D/E/H/L` 列留空，供人工补充。
- `K` 列写入 `=IF(Jn="","",In*Jn)`，未填单价时保持空白，填价后自动算合价。
- 末行为合计行：`A:G` 合并写“合 计”，`K` 列写入 `=SUM(K6:K{末行-1})`。
- 复用底版的字体（标题微软雅黑 16 白字、表头微软雅黑 11 白字、正文宋体 11）、填充色（`1E7B3C` / `E8F5E9`）、边框、列宽、行高、冻结窗格（`B6`）、打印区域、重复表头（`$1:$5`）、横向 A4 与筛选范围。
- 明细行数量变化时重建行并同步合计行、打印区域与筛选范围，不保留底版样例数据。

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `openpyxl` | 填充 Excel 模板 |
| `LLMFactory.get_light()` | 备注字段生成（可选，仅少量 token） |
| `LLMCallLogger.log()` | 成本记录（调用了 LLM 才记） |
| `PurchaseOrderService.get_order_with_project_scoped()` | 获取采购清单与所属项目名称 |
| `KnowledgeBaseManager.save_purchase_record()` | 记录询价到长期记忆库 |
| `StorageInterface.save()` | 保存生成文件 |
| `app.models.inquiry.InquirySheet` | 写入数据库 |

---

## 4. 异常处理

| 异常 | 触发条件 | 处理策略 |
|:---- |:-------- |:-------- |
| `OrderNotFoundError` | 采购单不存在 | HTTP 404 |
| `EmptyOrderError` | 采购清单为空（无法填充） | HTTP 422 |
| `TemplateNotFoundError` | template_id 不存在 | HTTP 404 |
| `LLMUnavailableError` | 备注 LLM 调用失败 | 跳过备注生成，其余正常返回（备注字段置空） |
