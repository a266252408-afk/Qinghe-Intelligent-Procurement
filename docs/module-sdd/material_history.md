# SDD — 长期材料历史服务（material_history）

> **代码位置**：`backend/app/services/material_history.py`
> **定位**：供应商材料报价历史的落库、去重、查询与向量索引。
> **约束**：所有查询强制带 `team_id`；不调用大模型。

---

## 1. 功能描述

把确认后的供应商报价写入长期材料历史，并在采购、收货环节更新履约信息：

- 报价确认入库：按完整业务字段生成指纹去重；
- 对话查询：按材料名或供应商名检索当前团队历史；
- 空结果指引：按关键词模糊匹配团队内已存在的供应商名（只返回名称，不返回记录）；
- 收货更新：写入成交价、下单时间、到货时间与收货状态；
- 向量索引：结构化记录为主数据，向量索引失败不影响落库。

---

## 2. 接口签名

```python
class MaterialHistoryService:
    @staticmethod
    async def search_for_chat(
        material_name: str,     # 对话中提取的材料名
        team_id: int,
        db: AsyncSession,
    ) -> list[MaterialHistoryOut]: ...

    @staticmethod
    async def suggest_suppliers(
        keyword: str,           # 查空的材料名/关键词
        team_id: int,
        db: AsyncSession,
    ) -> list[str]:
        """最多返回 3 个匹配的供应商名，供模型改用 supplier_name 重查。"""

    @staticmethod
    async def register_upload(
        team_id: int,
        user_id: int,
        file_path: str,
        original_name: str,
        db: AsyncSession,
    ) -> QuoteUpload: ...

    @staticmethod
    async def save_from_quote(
        quote: Quote,
        upload: QuoteUpload | None,
        team_id: int,
        confirmed_by: int,
        db: AsyncSession,
    ) -> int:
        """写入长期记忆，返回新增条数。"""

    @staticmethod
    async def list_records(
        filters: MaterialHistoryFilter,
        team_id: int,
        db: AsyncSession,
    ) -> list[MaterialHistoryOut]: ...

    @staticmethod
    async def update_from_receipt(
        receipt: Receipt,
        team_id: int,
        db: AsyncSession,
    ) -> int: ...
```

### 去重指纹

`_fingerprint` 对团队、供应商、材料、规格、数量、单位、报价、日期、有效期、
交期与付款条件等字段做 JSON 序列化后计算 SHA-256。同一团队内指纹相同则跳过，
避免重复确认同一份报价产生多条记录。

### 筛选条件

`MaterialHistoryFilter` 支持 `supplier_name`、`material_name`（模糊包含）、
`project_id`、`date_from`、`date_to`，结果按报价日期倒序。

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `MaterialHistoryRecord` / `QuoteUpload` | 长期记忆与上传记录 ORM |
| `PurchaseOrder` / `Project` / `Quote` / `Receipt` / `SupplierOrder` | 关联项目与履约信息 |
| `KnowledgeBaseManager.index_material_record` | 向量索引（best-effort） |
| `MaterialHistoryFilter` / `MaterialHistoryOut` | 请求与响应模型 |

---

## 4. 异常处理

- 材料名为空：`search_for_chat` / `suggest_suppliers` 直接返回空列表；
- 指纹重复：跳过该条，返回的新增计数不包含它；
- 向量索引失败：记录 warning，结构化记录照常保留，精确查询不受影响；
- 收货关联的供应商订单不存在：返回 0，不更新任何记录；
- 报价日期缺失：使用当前 UTC 日期；
- 采购单不存在导致项目无法解析：`project_id` 记为空。
