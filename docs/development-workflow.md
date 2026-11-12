# 开发流程手册 — 园林工程智能采购助手

> **文档定位**：SDD 驱动开发的操作手册，整合 CLAUDE.md §5、AGENTS.md §2 与项目宪法中的工作流要求。
> **适用对象**：所有施工者（Claude Code / 人类开发者）。
> **强制等级**：必须遵守，违反即视为未完成。

---

## 1. 核心开发理念

### 1.1 SDD 驱动（Source: CLAUDE.md §5.1）

**任何功能开发前，必须有对应的模块级 SDD（`docs/module-sdd/<module>.md`）。**

SDD 是代码的"施工图纸"，没有图纸不许施工。SDD 必须包含四要素（CLAUDE.md §5.2）：
1. **功能描述**：做什么（不超过 3 句话）
2. **接口签名**：核心方法签名 + 输入输出 Pydantic 模型
3. **外部依赖**：依赖哪些模块/库/大模型
4. **异常处理**：可能的异常与降级策略

### 1.2 骨架先行（Source: AGENTS.md §2.3）

**代码生成分两阶段**：
- **第一阶段（骨架）**：方法签名 + 类型注解 + docstring + pass，不写业务逻辑
- **人工核对**：对照 SDD 检查签名是否一致（10 秒/方法）
- **第二阶段（补全）**：确认骨架无误后补全业务逻辑

骨架阶段发现问题的修复成本 ≈ 0；逻辑写完再发现接口设计错的修复成本是 10 倍。

### 1.3 测试先行（Source: CLAUDE.md §5.1, §8）

**每实现一个模块，立即跑对应测试**：
- 后端：`pytest tests/test_<module>.py -v`
- 前端：`cd frontend && npm test -- components/<xxx>.test.ts`
- 覆盖率：核心模块（agents/services）100%，整体 ≥ 80%
- 大模型 Mock：测试中不调用真实 LLM API，用 Mock 对象返回预定义 Pydantic 模型实例

### 1.4 AI 辅助而非替代（Source: PRD §1.2）

**大模型做识别/提取/建议，人做确认/决策**。代码层面（AGENTS.md §4）：
- 大模型只用于：解析、对话、检索回答、比价建议、摘要压缩、意图路由
- 大模型不用于：纯 CRUD、状态机、权限校验、比价数值计算、文件路径管理

---

## 2. 标准开发流程

### 2.1 接收任务

1. 阅读 `CLAUDE.md` 确认项目宪法与红线
2. 阅读 `AGENTS.md` 确认角色定位与行为边界
3. 阅读对应 SDD 文档（`docs/module-sdd/<module>.md`）确认接口契约
4. 阅读 `docs/tasks/implementation.md` 确认任务依赖与状态

### 2.2 多文件改动规则（Source: AGENTS.md §2.2）

**涉及 3 个以上文件时，先用 Plan Mode 输出方案，等用户确认后再实现。**

### 2.3 两阶段代码生成

#### 第一阶段：骨架生成

严格要求：
1. 每个 public 方法只写：方法签名 + 类型注解 + docstring + pass
2. 不要写任何业务逻辑
3. 所有 import 语句写全
4. 使用 Pydantic 模型定义数据结构
5. 每个文件顶部写模块说明注释

#### 人工核对清单

- [ ] 方法名与 SDD 中接口签名一致
- [ ] 参数类型与 SDD 中描述一致
- [ ] 返回值类型与 SDD 中描述一致
- [ ] Pydantic 模型的字段与 JSON Schema 一致

#### 第二阶段：业务逻辑补全

按依赖顺序补全（system-design.md §3.1）：
1. **第一批（无依赖）**：storage、llm_factory、llm_logger
2. **第二批（依赖前者）**：auth_service、project_service、order_service、approval_service、knowledge_base_manager
3. **第三批（依赖 Service）**：6 个 Agent（router/list_parser/inquiry/compare/knowledge/chat）
4. **第四批（依赖 Agent）**：API 路由层

### 2.4 测试编写

- 每个 Service 必须有 `tests/test_<service>.py`
- 每个 Agent 必须有 `tests/test_<agent>.py`
- Mock 大模型返回预定义的 Pydantic 模型实例
- 命令：`pytest tests/ -v --cov=app --cov-report=term-missing`

### 2.5 对照 SDD 验收（Source: CLAUDE.md §5.1）

代码写完后对照 SDD 逐条验收，产出 `docs/tasks/acceptance_report.md`：
- SDD 条目 → 代码位置 → 状态（pass/fail/partial）
- 通过率 ≥ 95%（允许 1-2 个 partial 但必须修复）

### 2.6 更新施工日志（Source: CLAUDE.md §5.1）

每完成一个模块，更新 `docs/dev-log.md`：
- 完成内容
- 决策记录
- 遇到的坑
- 关联 commit

---

## 3. 多 Agent 协作开发（Source: CLAUDE.md §5.3）

复杂任务可拆分给多个 Agent 并行：
- 一个 Agent 负责一个模块的骨架
- 接口契约（Schema）先定义，再并行实现
- 实现完成后统一集成测试

### 3.1 协作规则

1. **接口契约先行**：所有 Agent 必须先遵循 `docs/schemas/` 下的 JSON Schema
2. **上下文隔离**：每个 Agent 只看自己模块的 SDD + 依赖模块的接口签名，不看实现
3. **集成测试统一**：所有 Agent 完成后，由主 Agent 统一跑集成测试

### 3.2 Agent 任务分配示例

| Agent | 负责模块 | 依赖 |
|:------|:---------|:-----|
| Agent A | llm_factory + llm_logger | 无 |
| Agent B | storage + auth | 无 |
| Agent C | project + order service | Agent B（auth） |
| Agent D | knowledge_base_manager | Agent A（llm_factory） |
| Agent E | 6 个 Agent（router/list_parser/inquiry/compare/knowledge/chat） | Agent A、C、D |

---

## 4. 层级职责硬规则（Source: CLAUDE.md §3）

| 层 | 职责 | 禁止 |
|:---|:-----|:-----|
| `api/` | 路由、参数校验、调用 service | 写业务逻辑、直接调用大模型 |
| `agents/` | 调用大模型、工具调度 | 直接操作数据库（通过 service） |
| `services/` | 业务逻辑、数据 CRUD | 调用大模型 |
| `models/` | 数据表定义 | 写业务逻辑 |
| `schemas/` | 请求/响应数据结构 | 写业务逻辑 |

---

## 5. 大模型调用规则（Source: AGENTS.md §3-4, CLAUDE.md §6）

### 5.1 必须通过 LLMFactory

```python
# 正确
from app.services.llm_factory import LLMFactory
llm = LLMFactory.get_light()

# 禁止（违反 CLAUDE.md §7 红线）
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(...)
```

### 5.2 每次调用必须记录日志

```python
await LLMCallLogger.log(
    agent_name="list_parser",
    model="deepseek-v3",
    input_tokens=500,
    output_tokens=200,
    cost=0.001,
    latency_ms=1200,
    cache_hit=False,
    session_id="xxx"
)
```

### 5.3 档位选择（tech-stack.md §7.2）

| 档位 | 适用任务 |
|:----- |:----- |
| 轻量档 | 结构化提取、分类、摘要、路由 |
| 中量档 | 对话、检索回答、趋势分析 |
| 重量档 | 复杂推理、比价建议 |

### 5.4 上下文拼接顺序（tech-stack.md §7.6）

System → 知识库 → 检索结果 → 摘要 → 最近N轮 → 当前输入

不易变的放上面（命中 Prompt Cache），易变的放尾部。

---

## 6. 代码审查流程（Source: development-workflow.md §2.5, CLAUDE.md §8）

### 6.1 触发时机

- 每个模块业务逻辑补全后
- 提交前自审
- 集成测试前统一审查

### 6.2 使用技能包

调用 `.claude/skills/code-review/` 技能包，对目标文件执行五维审查：
1. 编码规范
2. 逻辑正确性
3. 架构合规
4. 安全性
5. 可维护性

### 6.3 修复规则

- **严重问题**：必须立即修复，修复后重新审查
- **建议问题**：记录到 `docs/tasks/tech_debt.md`，后续处理

---

## 7. 提交规范（Source: CLAUDE.md §10）

### 7.1 Conventional Commits

格式：`<type>(<scope>): <description>`

- type：`feat` / `fix` / `refactor` / `docs` / `style` / `test` / `chore` / `perf`
- scope：`backend` / `frontend` / `docs` / `config` / `agent` / `service`

### 7.2 示例

```
feat(agent): add list parser agent with structured output
fix(service): correct team_id filter in order service
docs(prd): update acceptance criteria for compare feature
```

### 7.3 提交前检查

- [ ] 代码已通过 ruff/eslint 格式化
- [ ] 所有测试通过（`pytest tests/ -v`）
- [ ] 无硬编码 API Key
- [ ] .env 未被暂存
- [ ] commit message 符合规范

---

## 8. 红线清单（Source: CLAUDE.md §7, AGENTS.md §3）

施工者必须遵守以下红线，违反即视为未完成：

### 禁止
- 跳过 SDD 直接写代码
- 在业务逻辑中硬编码 API Key
- 删除或绕过测试代码
- 提交 .env 文件到 Git
- 前端组件直接调用大模型 API
- 业务层裸 SQL 绕过 team_id 过滤
- API 层直接调用大模型
- Agent 直接操作数据库
- 在未告知的情况下引入新的外部依赖

### 必须
- 修改函数签名时，同步更新所有调用方
- 所有 API 返回统一格式 `{"code": 0, "msg": "ok", "data": {...}}`
- 大模型调用通过 LLMFactory 获取实例
- 每次 LLM 调用后记录 LLMCallLogger.log()
- 上下文拼接遵循顺序：System → 知识库 → 检索结果 → 摘要 → 最近N轮 → 当前输入

---

**文档结束。施工者开工前必读，开发过程中随时参照。**
