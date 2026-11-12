# SDD — 下单管理服务

## 功能描述

采购单完成材料供应商选择并提交下单申请后，由管理员审批；审批通过时冻结供应商、报价、成交价快照，记录下单时间，并生成下单管理记录。
管理员可删除下单记录及其收货单，采购单和长期材料历史保留。

## 接口签名

- `PurchaseOrderService.list_supplier_options(order_id, team_id, db)`：返回采购项对应的团队供应商报价。
- `PurchaseOrderService.create_supplier_order(order_id, team_id, db)`：审批通过后创建幂等下单记录。
- `SupplierOrderService.export(supplier_order_id, team_id, file_format, db, item_id)`：导出整单或明细 CSV/Excel。
- `SupplierOrderService.delete(supplier_order_id, team_id, db)`：删除下单记录及关联收货单。

## 外部依赖

SQLAlchemy、openpyxl、采购单/报价服务和团队权限校验。

## 异常处理

跨团队或不存在的记录返回 404；非审批通过状态不能生成下单记录；导出格式仅支持 CSV 和 XLSX。
