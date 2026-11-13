# 实现任务追踪 — 园林工程智能采购助手

> 本文根据 2026-08-26 工作区代码、Alembic 迁移、测试结果和运行状态更新。
> 这里记录的是当前施工状态，不再沿用早期“只有骨架”的阶段描述。

## 状态说明

- `done`：代码、接口或文档已落地，并有对应验证。
- `partial`：主要功能已落地，但仍有明确的验证或交付项未完成。
- `pending`：尚未完成，不能视为已交付。
- `skeleton`：只有接口或基础骨架，业务逻辑未完成。

## 阶段 0：项目脚手架

| 任务 | 状态 | 当前内容 |
|:---|:---:|:---|
| T0.1 Git 仓库初始化 | done | `.gitignore`、`.env.example` 和 Git 仓库已建立 |
| T0.2 开发流程文档 | done | `docs/development-workflow.md`、`docs/dev-log.md`、本文档 |
| T0.3 代码审查技能包 | done | `.claude/skills/code-review/` 已建立 |

## 阶段 1：基础设施 SDD 与 Schema

| 任务 | 状态 | 当前内容 |
|:---|:---:|:---|
| T1.1 LLM 工厂 SDD | done | `docs/module-sdd/llm_factory.md` |
| T1.2 LLM 日志服务 SDD | done | `docs/module-sdd/llm_logger_service.md` |
| T1.3 文件存储服务 SDD | done | `docs/module-sdd/storage_service.md` |
| T1.4 认证权限服务 SDD | done | `docs/module-sdd/auth_service.md` |
| T1.5 基础 Schema | done | `docs/schemas/common.json`、`auth.json` |

## 阶段 2：Service 层 SDD 与 Schema

| 任务 | 状态 | 当前内容 |
|:---|:---:|:---|
| T2.1 项目管理服务 SDD | done | 项目创建、查询、修改、软删除和团队隔离 |
| T2.2 采购单管理服务 SDD | done | 采购单状态机、采购项、供应商选择、询价和比价 |
| T2.3 审批流服务 SDD | done | 审批通过、驳回、审批历史和权限校验 |
| T2.4 知识库管理服务 SDD | done | 行业知识、会话消息和长期材料历史 |
| T2.5 Service 层 Schema | done | 当前 Schema 已扩展到认证、项目、采购、报价、收货、长期材料等模块 |

## 阶段 3：Agent 层 SDD 与 Schema

| 任务 | 状态 | 当前内容 |
|:---|:---:|:---|
| T3.1 Router Agent SDD | done | 文件路由、斜杠命令和长期材料问题规则路由 |
| T3.2 清单解析 Agent SDD | done | CSV/表格清单结构化解析和人工核对提示 |
| T3.3 询价单 Agent SDD | done | 询价单模板选择和文件生成 |
| T3.4 比价 Agent SDD | done | 单价、总价、交付、付款和历史因素的确定性计算 |
| T3.5 知识库 Agent SDD | done | 行业文档混合检索、证据保留和模型整理回答 |
| T3.6 对话 Agent SDD | done | SSE 对话、上下文压缩和长期材料标准工具调用闭环 |
| T3.7 Agent 层 Schema | done | 路由、清单、报价、比价、知识库、对话 Schema 已落地 |

## 阶段 4：后端基础设施

| 任务 | 状态 | 当前内容 |
|:---|:---:|:---|
| T4.1 后端依赖与配置 | done | Python 3.11、FastAPI、SQLAlchemy、Alembic 和环境配置 |
| T4.2 FastAPI 入口与核心配置 | done | `main.py`、统一响应、全局异常、CORS、健康检查 |
| T4.3 数据库基类与会话 | done | 异步 SQLite、WAL、外键约束、请求级数据库会话 |
| T4.4 SQLAlchemy 数据模型 | done | 当前 24 张关系数据库表对应的 ORM 模型已落地 |
| T4.5 Pydantic Schema | done | API 和 Agent 使用的请求/响应模型已落地 |

## 阶段 5：Service 与 Agent 业务逻辑

| 任务 | 状态 | 当前内容 |
|:---|:---:|:---|
| T5.1 基础设施 Service | done | LLMFactory、LLMCallLogger、LocalStorage |
| T5.2 基础设施 Service 业务逻辑 | done | 三档模型缓存、调用日志、文件安全存储和格式校验 |
| T5.3 业务 Service | done | 认证、项目、采购单、审批、报价、知识库、长期材料、下单、收货 |
| T5.4 业务 Service 业务逻辑 | done | CRUD、状态机、团队隔离、报价确认和收货回写已实现 |
| T5.5 Agent | done | Router、ListParser、Inquiry、Compare、Knowledge、Chat |
| T5.6 Agent 业务逻辑 | done | 模型调用均通过 LLMFactory；ChatAgent 支持标准工具闭环 |
| T5.7 单元测试 | done | 后端测试文件已覆盖核心 Service 和 Agent |

## 阶段 6：API 路由与集成测试

| 任务 | 状态 | 当前内容 |
|:---|:---:|:---|
| T6.1 API 依赖注入 | done | JWT 当前用户、数据库会话和团队 ID 依赖 |
| T6.2 业务路由 | done | 认证、项目、采购单、审批、报价、知识库、收货路由 |
| T6.3 对话 SSE 路由 | done | `/api/chat` 使用标准 SSE 输出，关闭代理缓冲 |
| T6.4 集成测试 | done | `backend/tests/test_api.py` 覆盖认证、项目、采购、审批、下单和收货流程 |

## 阶段 7：前端实现

| 任务 | 状态 | 当前内容 |
|:---|:---:|:---|
| T7.1 前端脚手架 | done | Vue 3、Vite、Element Plus、Pinia、ECharts |
| T7.2 路由、Store、API 客户端 | done | 登录身份、项目/会话选择、统一 Axios 和 SSE 客户端 |
| T7.3 登录与团队功能 | done | 登录、注册、团队邀请、加入/退出团队和权限展示集成在登录页及侧栏 |
| T7.4 主对话页 | done | `Home.vue`、聊天窗口、附件上传、SSE 流式渲染和结构化结果抽屉 |
| T7.5 业务视图 | done | 项目、采购单、报价、审批、知识库、长期材料、下单、收货页面 |
| T7.6 业务组件 | done | 采购项编辑、报价/比价展示、ECharts 柱状图和雷达图 |

## 阶段 8：部署与知识库初始化

| 任务 | 状态 | 当前内容 |
|:---|:---:|:---|
| T8.1 CI/CD | done | `.github/workflows/ci.yml` 执行后端测试覆盖率和前端构建 |
| T8.2 知识库种子数据 | pending | 当前没有纳入仓库的行业知识种子文档、词典和模板数据交付包 |
| T8.3 容器化交付 | done | 后端与前端 Dockerfile、`docker-compose.yml`、Nginx 反向代理与命名卷；本地构建验证 |

## 阶段 9：验收与回归

| 任务 | 状态 | 当前内容 |
|:---|:---:|:---|
| T9.1 SDD 验收报告 | pending | 尚未形成独立的 SDD → 代码追溯报告 |
| T9.2 代码审查 | pending | 仍需按五维清单完成一次独立审查并记录结论 |
| T9.3 全量回归 | partial | 后端全量测试 `100 passed`，Python 编译和 diff 检查通过；前端 `npm run build` 成功（2149 modules），但当前没有可执行的业务测试文件 |

## 当前进度

| 阶段 | 完成情况 |
|:---|:---:|
| 阶段 0-4 | 25/25 完成 |
| 阶段 5 | 7/7 完成 |
| 阶段 6 | 4/4 完成 |
| 阶段 7 | 6/6 完成 |
| 阶段 8 | 3/4 完成，1 项待施工 |
| 阶段 9 | 0 项完全完成，1 项部分完成，2 项待施工 |
| **总计** | **45/49 完全完成，1 项部分完成，3 项存在待验收或待施工内容** |

## 当前运行与验证基线

- 后端：`http://127.0.0.1:8000`，健康检查返回 `{"code":0,"msg":"ok","data":{"status":"ok"}}`。
- 前端开发服务：`http://127.0.0.1:5173`。
- 数据库：`backend/data/app.db`，结构由 `backend/alembic/versions/` 管理。
- 后端测试：`100 passed`。
- 关键能力：采购清单解析、报价解析与确认、比价、审批、供应商下单、收货确认、行业知识检索、长期材料历史查询、SSE 对话。
- 长期材料对话使用 `assistant tool_calls → role=tool → tool_call_id → assistant` 标准闭环；DeepSeek 思考模式首轮使用 `tool_choice=auto`。

## 尚未完成的施工项

1. 准备可版本化的行业知识、专业词典和模板种子数据，并补充初始化流程。
2. 产出 SDD 验收追溯报告和独立代码审查记录。
3. 为前端补充 Vitest 业务组件测试；当前 CI 已有前端构建，但没有业务测试用例。

---

**文档结束。每完成一个待办项，应同步更新本文件和 `docs/dev-log.md`。**
