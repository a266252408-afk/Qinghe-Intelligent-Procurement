# 数据库表与字段说明

> 适用版本：2026-08-26
>
> 本文对应 `backend/app/models/` 下的 SQLAlchemy 模型，以及
> `backend/alembic/versions/` 中已定义的迁移。当前关系数据库为
> `backend/data/app.db`（SQLite）。如果迁移文件、ORM 模型和实际数据库不一致，
> 应以迁移后的实际结构为准，并先执行迁移再运行服务。

## 1. 数据库范围

当前关系数据库包含 24 张业务和运维表，另有 1 张 Alembic 迁移元数据表：

```text
users, teams, team_members, team_invitations
projects, purchase_orders, purchase_items
suppliers, quotes, quote_items, inquiry_sheets
approval_records
industry_knowledge, conversation_sessions, messages
quote_uploads, material_history_records
supplier_orders, supplier_order_items, receipts, receipt_items
audit_logs, llm_call_logs, llm_cache
```

`alembic_version` 不属于业务模型，由 Alembic 自动维护，用于记录当前数据库已经执行到的迁移版本。

所有 ORM 表都继承 `Base`，因此都包含以下公共字段：

| 字段 | 类型 | 可空 | 作用 |
|:---|:---|:---:|:---|
| `created_at` | DateTime | 否 | 记录创建时间，默认使用 UTC 时间 |
| `updated_at` | DateTime | 否 | 最近一次更新时间，更新实体时自动刷新 |

字段类型说明：`Numeric(p,s)` 用于金额或数量，避免使用浮点数保存业务金额；`JSON` 用于保存结构化快照；`Date` 只有日期；`DateTime` 保存日期和时间。

## 2. 账号与团队

### 2.1 `users` — 用户账号

用户登录身份、密码哈希和账号类型。密码明文不入库。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 用户 ID |
| `username` | String(50) | 否 | 唯一 | 登录用户名 |
| `password_hash` | String(255) | 否 |  | bcrypt 密码哈希 |
| `display_name` | String(100) | 否 | 默认空字符串 | 页面展示名称 |
| `account_type` | String(20) | 否 | `purchaser` | 账号类型，当前支持 `admin`、`purchaser` |

### 2.2 `teams` — 团队

团队是业务数据隔离的根节点。项目、供应商、行业知识、长期材料、下单和收货等数据通过团队直接或间接隔离。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 团队 ID |
| `name` | String(100) | 否 |  | 团队名称 |
| `creator_id` | Integer | 否 | 外键 `users.id` | 创建团队的用户 |
| `invite_code` | String(10) | 否 | 唯一 | 邀请采购员加入团队的邀请码 |

### 2.3 `team_members` — 团队成员关系

记录用户属于哪个团队以及在团队中的角色。当前迁移限制一个用户同时只能有一条团队成员关系。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 关系 ID |
| `team_id` | Integer | 否 | 外键 `teams.id` | 所属团队 |
| `user_id` | Integer | 否 | 外键 `users.id`，当前唯一 | 成员用户 |
| `role` | String(20) | 否 |  | `owner` 团队管理员或 `member` 普通成员 |

### 2.4 `team_invitations` — 团队邀请

记录管理员邀请采购员加入团队的过程，采购员需要明确接受或拒绝。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 邀请 ID |
| `team_id` | Integer | 否 | 外键 `teams.id` | 被邀请加入的团队 |
| `inviter_id` | Integer | 否 | 外键 `users.id` | 发起邀请的管理员 |
| `invitee_id` | Integer | 否 | 外键 `users.id` | 被邀请用户 |
| `status` | String(20) | 否 | `pending` | `pending`、`accepted`、`rejected` 等邀请状态 |

## 3. 项目与采购单

### 3.1 `projects` — 工程项目

团队下的园林工程项目。项目删除采用软删除，已删除项目不参与正常列表和同名校验。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 项目 ID |
| `team_id` | Integer | 否 | 外键 `teams.id` | 所属团队 |
| `name` | String(100) | 否 | 当前团队未删除项目内唯一 | 项目名称 |
| `owner_id` | Integer | 否 | 外键 `users.id` | 项目创建人/负责人 |
| `budget` | Numeric(12,2) | 是 |  | 项目预算 |
| `status` | String(20) | 否 | `active` | 项目状态 |
| `remark` | Text | 是 |  | 项目备注 |
| `is_deleted` | Boolean | 否 | `false` | 是否软删除 |

### 3.2 `purchase_orders` — 采购单

采购流程的主单据。采购单属于项目，采购项保存在 `purchase_items`。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 采购单 ID |
| `project_id` | Integer | 否 | 外键 `projects.id` | 所属项目 |
| `creator_id` | Integer | 否 | 外键 `users.id` | 创建人 |
| `name` | String(120) | 是 |  | 采购单自定义名称 |
| `status` | String(30) | 否 | `draft` | `draft`、`pending_approval`、`approved`、`ordered`、`received`、`settled`、`rejected` |
| `total_amount` | Numeric(12,2) | 是 |  | 采购单金额合计 |
| `remark` | Text | 是 |  | 采购单备注 |

### 3.3 `purchase_items` — 采购项

采购清单中的材料明细，也保存提交审批时选择的供应商和成交价。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 采购项 ID |
| `order_id` | Integer | 否 | 外键 `purchase_orders.id`，删除级联 | 所属采购单 |
| `species` | String(100) | 否 |  | 材料/苗木品种 |
| `spec` | String(100) | 否 |  | 规格 |
| `quantity` | Numeric(10,2) | 否 |  | 数量 |
| `unit` | String(20) | 否 |  | 单位，如株、平方米 |
| `unit_price` | Numeric(10,2) | 是 |  | 初始或清单单价 |
| `total_price` | Numeric(12,2) | 是 |  | 清单行总价 |
| `supplier_name` | String(100) | 是 |  | 选定供应商名称 |
| `supplier_quote_item_id` | Integer | 是 | 外键 `quote_items.id` | 对应的供应商报价项 |
| `supplier_quote_price` | Numeric(10,2) | 是 |  | 供应商原始报价单价 |
| `final_price` | Numeric(10,2) | 是 |  | 人工确认的成交单价 |

## 4. 供应商、报价与询价

### 4.1 `suppliers` — 供应商

团队级供应商基础档案，报价单可以通过 `supplier_id` 关联，也可以保留文件解析出的供应商名称。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 供应商 ID |
| `team_id` | Integer | 否 | 外键 `teams.id` | 所属团队 |
| `name` | String(100) | 否 |  | 供应商名称 |
| `contact` | String(50) | 是 |  | 联系人 |
| `phone` | String(30) | 是 |  | 联系电话 |
| `main_category` | String(100) | 是 |  | 主营品类 |
| `rating` | Numeric(3,1) | 是 |  | 历史合作评分，目标范围 0-5 |
| `remark` | Text | 是 |  | 供应商备注 |

### 4.2 `quotes` — 供应商报价单

上传并解析后的报价单主记录。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 报价单 ID |
| `order_id` | Integer | 否 | 外键 `purchase_orders.id` | 对应采购单 |
| `supplier_id` | Integer | 是 | 外键 `suppliers.id` | 对应供应商档案 |
| `supplier_name` | String(100) | 是 |  | 文件解析或人工填写的供应商名称 |
| `file_path` | String(500) | 否 |  | 上传文件相对存储路径 |
| `parsed_data_json` | JSON | 是 |  | 原始解析结果备份 |
| `quote_date` | Date | 是 |  | 报价日期 |

### 4.3 `quote_items` — 报价项

报价单中的材料明细，用于报价展示、比价和采购项供应商选择。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 报价项 ID |
| `quote_id` | Integer | 否 | 外键 `quotes.id`，删除级联 | 所属报价单 |
| `species` | String(100) | 否 |  | 材料/苗木品种 |
| `spec` | String(100) | 否 |  | 规格 |
| `unit` | String(20) | 否 | 默认空字符串 | 单位 |
| `unit_price` | Numeric(10,2) | 是 |  | 供应商报价单价 |
| `final_price` | Numeric(10,2) | 是 |  | 最终成交单价 |
| `quantity` | Numeric(10,2) | 是 |  | 报价数量 |
| `total_price` | Numeric(12,2) | 是 |  | 报价总价 |
| `delivery_days` | Integer | 是 |  | 交付天数 |
| `payment_terms` | Text | 是 |  | 付款条件 |
| `valid_until` | Date | 是 |  | 报价有效期截止日期 |

### 4.4 `inquiry_sheets` — 询价单文件记录

记录根据采购单生成的询价文件，文件本体保存在本地存储，不直接存入数据库。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 询价单记录 ID |
| `order_id` | Integer | 否 | 外键 `purchase_orders.id` | 对应采购单 |
| `template_id` | String(50) | 否 |  | 使用的询价模板标识 |
| `file_path` | String(500) | 否 |  | 生成文件相对路径 |

## 5. 审批与知识库

### 5.1 `approval_records` — 审批记录

采购单提交审批后的每次审批决定，不保存为采购单状态的替代品，而是保存操作历史。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 审批记录 ID |
| `order_id` | Integer | 否 | 外键 `purchase_orders.id` | 被审批采购单 |
| `approver_id` | Integer | 否 | 外键 `users.id` | 审批人 |
| `decision` | String(20) | 否 |  | `approved` 或 `rejected` |
| `reason` | Text | 是 |  | 驳回原因或审批说明 |

### 5.2 `industry_knowledge` — 行业知识文档索引

保存行业知识文档的结构化索引和文本分块；向量数据本体保存在 Chroma，`vector_id` 用于关联。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 文档分块记录 ID |
| `team_id` | Integer | 否 | 外键 `teams.id` | 文档所属团队 |
| `source_file` | String(500) | 否 |  | 来源文件名或路径 |
| `content` | Text | 否 |  | 清洗后的文本分块 |
| `vector_id` | String(100) | 是 |  | Chroma 向量文档 ID |

### 5.3 `conversation_sessions` — 对话会话

保存用户与 AI 的会话容器。`project_id` 可以为空，表示不绑定具体项目的对话。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 会话 ID |
| `user_id` | Integer | 否 | 外键 `users.id` | 会话所属用户 |
| `project_id` | Integer | 是 | 外键 `projects.id` | 可选的关联项目 |
| `title` | String(200) | 否 | `新会话` | 会话标题 |

### 5.4 `messages` — 对话消息

保存会话中的用户消息和 AI 消息，历史摘要和结构化结果可放在 `metadata_json`。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 消息 ID |
| `session_id` | Integer | 否 | 外键 `conversation_sessions.id`，删除级联 | 所属会话 |
| `role` | String(20) | 否 |  | `user` 或 `assistant` |
| `content` | Text | 否 |  | 消息文本 |
| `metadata_json` | JSON | 是 |  | 附件信息、结构化结果等扩展数据 |

## 6. 长期材料记忆

### 6.1 `quote_uploads` — 报价文件上传记录

记录报价文件的上传来源和人工确认状态。文件本体在本地存储，数据库只保存路径和元数据。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 上传记录 ID |
| `team_id` | Integer | 否 | 外键 `teams.id` | 所属团队 |
| `uploaded_by` | Integer | 否 | 外键 `users.id` | 上传人 |
| `file_path` | String(500) | 否 |  | 文件相对路径 |
| `original_name` | String(255) | 否 |  | 用户上传时的原始文件名 |
| `confirmed_by` | Integer | 是 | 外键 `users.id` | 确认保存报价的用户 |
| `confirmed_at` | DateTime | 是 |  | 报价确认时间 |

### 6.2 `material_history_records` — 长期材料历史明细

按材料行保存团队共享的报价、成交和收货历史，是“桂花的历史成交价”等查询的确定性数据源。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 历史记录 ID |
| `team_id` | Integer | 否 | 外键 `teams.id` | 数据所属团队，查询必须隔离 |
| `supplier_name` | String(100) | 否 |  | 供应商名称 |
| `material_name` | String(100) | 否 |  | 材料名称 |
| `spec` | String(100) | 否 | 默认空字符串 | 材料规格 |
| `quantity` | Numeric(10,2) | 是 |  | 数量 |
| `unit` | String(20) | 否 | 默认空字符串 | 单位 |
| `quote_price` | Numeric(10,2) | 是 |  | 报价单价 |
| `total_price` | Numeric(12,2) | 是 |  | 报价总价 |
| `final_price` | Numeric(10,2) | 是 |  | 成交单价 |
| `quote_date` | Date | 是 |  | 报价日期 |
| `valid_until` | Date | 是 |  | 报价有效期 |
| `delivery_days` | Integer | 是 |  | 报价交付天数 |
| `payment_terms` | Text | 是 |  | 付款条件 |
| `source_file` | String(500) | 否 |  | 原始报价文件路径/名称 |
| `source_quote_id` | Integer | 是 | 外键 `quotes.id` | 来源报价单 |
| `uploaded_by` | Integer | 是 | 外键 `users.id` | 报价上传人 |
| `confirmed_by` | Integer | 是 | 外键 `users.id` | 报价确认人 |
| `fingerprint` | String(64) | 否 | 与 `team_id` 联合唯一 | 防止同一团队重复写入同一报价行 |
| `ordered_at` | DateTime | 是 |  | 实际下单时间 |
| `arrived_at` | DateTime | 是 |  | 实际到货时间 |
| `receipt_status` | String(20) | 是 |  | 收货状态 |

## 7. 下单与收货

### 7.1 `supplier_orders` — 供应商下单记录

管理员审批通过后生成的下单主记录。一张采购单最多对应一张下单记录。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 下单记录 ID |
| `purchase_order_id` | Integer | 否 | 外键 `purchase_orders.id`，联合唯一 | 来源采购单 |
| `team_id` | Integer | 否 | 外键 `teams.id` | 所属团队 |
| `status` | String(20) | 否 | `ordered` | 下单状态 |
| `ordered_at` | DateTime | 否 |  | 下单时间 |

### 7.2 `supplier_order_items` — 下单明细快照

冻结审批通过时的材料、供应商和价格，避免后续报价变化影响历史下单数据。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 下单明细 ID |
| `supplier_order_id` | Integer | 否 | 外键 `supplier_orders.id`，删除级联 | 所属下单记录 |
| `purchase_item_id` | Integer | 是 | 外键 `purchase_items.id`，删除置空 | 来源采购项 |
| `species` | String(100) | 否 |  | 材料/苗木品种快照 |
| `spec` | String(100) | 否 | 默认空字符串 | 规格快照 |
| `quantity` | Numeric(10,2) | 否 |  | 数量快照 |
| `unit` | String(20) | 否 | 默认空字符串 | 单位快照 |
| `supplier_name` | String(100) | 是 |  | 供应商快照 |
| `supplier_quote_price` | Numeric(10,2) | 是 |  | 供应商报价快照 |
| `final_price` | Numeric(10,2) | 是 |  | 成交价快照 |
| `total_price` | Numeric(12,2) | 是 |  | 下单行总价快照 |

### 7.3 `receipts` — 收货单

一张供应商下单记录对应一张收货单，支持待收货、部分收货等流程状态。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 收货单 ID |
| `supplier_order_id` | Integer | 否 | 外键 `supplier_orders.id`，唯一 | 对应下单记录 |
| `team_id` | Integer | 否 | 外键 `teams.id` | 所属团队 |
| `status` | String(20) | 否 | `pending` | 收货单状态 |
| `confirmed_at` | DateTime | 是 |  | 整单确认时间 |

### 7.4 `receipt_items` — 收货明细

按材料逐项记录实际到货时间和确认状态。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 收货明细 ID |
| `receipt_id` | Integer | 否 | 外键 `receipts.id`，删除级联 | 所属收货单 |
| `supplier_order_item_id` | Integer | 是 | 外键 `supplier_order_items.id`，删除置空 | 来源下单明细 |
| `species` | String(100) | 否 |  | 材料/苗木品种 |
| `spec` | String(100) | 否 | 默认空字符串 | 规格 |
| `quantity` | Numeric(10,2) | 否 |  | 收货数量 |
| `unit` | String(20) | 否 | 默认空字符串 | 单位 |
| `supplier_name` | String(100) | 是 |  | 供应商名称 |
| `final_price` | Numeric(10,2) | 是 |  | 成交价 |
| `arrived_at` | DateTime | 是 |  | 到货时间 |
| `is_received` | Boolean | 否 | `false` | 是否已确认该项收货 |

## 8. 审计与模型运维

### 8.1 `audit_logs` — 业务审计日志

记录创建、修改、删除、审批等关键操作。`target_id` 是多态目标 ID，必须结合 `target_type` 解读，没有单一外键。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 审计记录 ID |
| `team_id` | Integer | 否 | 外键 `teams.id` | 所属团队 |
| `user_id` | Integer | 否 | 外键 `users.id` | 操作人 |
| `action` | String(50) | 否 |  | `create`、`update`、`delete`、`approve`、`reject` 等 |
| `target_type` | String(50) | 否 |  | 目标类型，如 `PurchaseOrder` |
| `target_id` | Integer | 否 | 无多态外键 | 目标记录 ID |
| `diff_json` | JSON | 是 |  | 修改前后差异或操作详情 |

### 8.2 `llm_call_logs` — 大模型调用日志

开发者运维表，用于统计模型、Token、成本和延迟。该表刻意没有 `team_id`，不能作为团队业务数据查询来源。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 调用日志 ID |
| `agent_name` | String(50) | 否 |  | 发起调用的 Agent/模块 |
| `model` | String(100) | 否 |  | 使用的模型名称 |
| `input_tokens` | Integer | 否 | `0` | 输入 Token 数 |
| `output_tokens` | Integer | 否 | `0` | 输出 Token 数 |
| `cost` | Float | 否 | `0.0` | 估算成本，单位元 |
| `latency_ms` | Integer | 否 | `0` | 调用耗时，单位毫秒 |
| `cache_hit` | Boolean | 否 | `false` | 是否命中缓存 |
| `session_id` | String(100) | 否 | 空字符串 | 关联会话标识，可为空语义但字段本身非空 |

### 8.3 `llm_cache` — 大模型本地缓存

预留的模型响应缓存表。缓存键由模型、系统提示和用户输入等内容计算得出。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `id` | Integer | 否 | 主键，自增 | 缓存记录 ID |
| `prompt_hash` | String(64) | 否 | 唯一、有索引 | Prompt 缓存键 |
| `model` | String(100) | 否 |  | 模型名称 |
| `response` | Text | 否 |  | 序列化后的模型响应 |

### 8.4 `alembic_version` — Alembic 迁移版本

数据库结构管理表，不参与业务查询，也不应由业务代码写入。

| 字段 | 类型 | 可空 | 约束/默认值 | 作用 |
|:---|:---|:---:|:---|:---|
| `version_num` | VARCHAR(32) | 否 | 主键 | 当前已执行的 Alembic revision ID |

## 9. 关系、索引与约束

### 9.1 核心业务链路

```text
users ── team_members ── teams
  │                         │
  ├── projects ── purchase_orders ── purchase_items
  │                     │                    │
  │                     ├── quotes ── quote_items
  │                     ├── approval_records
  │                     └── supplier_orders ── supplier_order_items
  │                                                │
  └── conversation_sessions ── messages          └── receipts ── receipt_items

quote_uploads ──(确认)── material_history_records
industry_knowledge ──(vector_id)── Chroma 向量库
```

### 9.2 重要唯一约束

- `users.username` 唯一。
- `teams.invite_code` 唯一。
- `team_members.user_id` 唯一，当前一个账号只能加入一个团队。
- `team_invitations(team_id, invitee_id, status)` 联合唯一。
- `projects(team_id, name)` 对未删除项目唯一；删除后可以重新使用项目名称。
- `material_history_records(team_id, fingerprint)` 联合唯一，用于团队内去重。
- `supplier_orders.purchase_order_id` 唯一，一张采购单只能生成一张下单记录。
- `receipts.supplier_order_id` 唯一，一张下单记录只能生成一张收货单。
- `llm_cache.prompt_hash` 唯一。

### 9.3 删除行为

- 删除采购单的采购项、供应商下单及其下单明细按模型/迁移配置级联或由 Service 清理。
- 删除报价单会级联删除 `quote_items`。
- 删除会话会级联删除 `messages`。
- 删除收货单会级联删除 `receipt_items`。
- 下单明细和收货明细指向来源采购项时使用 `SET NULL`，保留下单/收货快照。
- 项目业务删除是软删除，不应直接删除项目历史数据。

## 10. 团队隔离与数据安全

- 业务数据直接带 `team_id`，或通过 `project_id`、`order_id`、`supplier_order_id` 等父实体间接归属团队。
- Service 和 API 查询必须先校验当前用户团队，再查询业务实体；长期材料查询必须使用当前团队的 `team_id`。
- `users.password_hash` 只保存哈希，文件字段只保存服务端相对路径或来源标识。
- `audit_logs`、`llm_call_logs` 和 `llm_cache` 是运维/审计数据，不应由普通业务查询直接展示给用户。
- `industry_knowledge` 只保存文本索引，向量数据位于 `chroma/`，它不是 SQLite 表。
- 当前数据库连接使用 SQLite WAL 和外键约束；生产环境若改用 PostgreSQL，需要同步检查迁移、连接池和并发写入策略。

## 11. 数据库维护入口

| 用途 | 位置/命令 |
|:---|:---|
| ORM 表定义 | `backend/app/models/*.py` |
| 所有模型导入 | `backend/app/models/__init__.py` |
| 数据库连接与初始化 | `backend/app/db/session.py` |
| 迁移配置 | `backend/alembic.ini`、`backend/alembic/env.py` |
| 迁移文件 | `backend/alembic/versions/` |
| 当前 SQLite 文件 | `backend/data/app.db` |
| 升级数据库 | `cd backend; alembic upgrade head` |
| 查看迁移版本 | `cd backend; alembic current` |

当前迁移头：`b7e4c6d2a910`。

不要直接手工修改 `app.db` 的表结构；任何结构变更都应先修改 ORM/迁移设计，再新增 Alembic migration，并补充对应测试和本文档。
