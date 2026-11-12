# SDD - 报价单管理（quote）

## 1. 功能描述

报价文件先由 QuoteParserAgent 解析为待确认结果，用户修改供应商名称和报价项目后，通过 QuoteService 确认写入 quotes 与 quote_items。所有查询和写入均通过采购单所属项目校验 team_id。

## 2. 接口

- POST /api/quotes/parse：上传报价文件并返回待确认项目。
- POST /api/quotes：确认保存报价。
- GET /api/quotes?order_id={id}&project_id={id}：按绑定采购单或项目查询已确认报价。
- DELETE /api/quotes/{id}：删除报价管理记录，长期材料历史保留。
- POST /api/orders/{id}/compare：对多个已确认报价执行比价并返回图表数据。

报价解析支持 .xlsx、.csv、.txt，识别品种、规格、数量、单价、总价、交货期和付款条件。解析结果不自动入库，必须经过用户确认。

## 3. 异常处理

- 文件格式或表头不符合要求：返回 422，保留统一 API 响应格式。
- 采购单不属于当前团队：返回 404。
- 没有报价时执行比价：返回 422，提示先上传报价文件。
