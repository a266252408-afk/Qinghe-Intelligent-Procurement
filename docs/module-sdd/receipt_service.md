# SDD — 收货管理服务

## 功能描述

下单审批通过时同步创建收货单。人工填写各材料货到时间，可逐项确认或在所有时间填写后一次确认全部收货；全部确认后同步采购单状态和长期材料记忆。
管理员可删除收货单，删除不影响下单快照和长期材料历史。

## 接口签名

- `ReceiptService.create_for_supplier_order(supplier_order_id, team_id, db)`：幂等创建收货单。
- `ReceiptService.update_receipt(receipt_id, data, team_id, db)`：保存到货时间和逐项确认。
- `ReceiptService.confirm_all(receipt_id, team_id, db)`：校验所有到货时间后完成收货。
- `ReceiptService.delete(receipt_id, team_id, db)`：删除收货单及明细。

## 外部依赖

SQLAlchemy、采购单/下单快照服务、`MaterialHistoryService`。

## 异常处理

跨团队或不存在的收货单返回 404；缺少到货时间不能确认；全部明细确认后状态更新为 `received`。
