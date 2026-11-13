# 技术选型文档 — 园林工程智能采购助手

> **文档定位**：基于 `docs/PRD.md` 的需求，记录技术栈选型决策、对比分析与扩展路径。是 `system-design.md`（系统架构）与 `CLAUDE.md`（项目宪法）的技术依据。
> **文档来源**：6 轮技术选型采访 + 1 轮成本优化与多 Agent 架构补充采访采集整理而成。
> **版本**：v1.1（新增第7章成本优化与多模型多 Agent 架构）

---

## 1. 选型决策总览

### 1.1 技术栈速览表

| 层次 | 选型 | 用途 |
|:----- |:----- |:----- |
| **后端语言** | Python 3.11 | 主开发语言 |
| **后端框架** | FastAPI + Pydantic v2 | Web 框架 + 数据校验 |
| **后端风格** | 全异步（async/await） | 支持流式输出 |
| **API 风格** | RESTful + OpenAPI | 接口规范 + 自动文档 |
| **数据库** | SQLite | 关系型存储 |
| **ORM** | SQLAlchemy 2.0（异步） | 数据访问层抽象 |
| **迁移工具** | Alembic | Schema 版本管理 |
| **文件存储** | 本地文件系统 | 上传文件存储 |
| **前端框架** | Vue 3 + Vite + Pinia | 前端开发 |
| **HTTP 客户端** | Axios | 前端调用后端 API |
| **UI 组件库** | Element Plus | 后台管理组件 |
| **图表库** | ECharts | 比价/趋势可视化 |
| **Markdown 渲染** | markdown-it | 对话消息渲染 |
| **大模型集成层** | LangChain | LLM 应用框架 |
| **流式协议** | SSE（Server-Sent Events） | 大模型流式输出 |
| **结构化输出** | Pydantic + 结构化输出 | 清单/报价 JSON 解析 |
| **嵌入模型** | 与大模型同供应商 | RAG 向量嵌入 |
| **向量库** | Chroma | 语义检索存储 |
| **关键词检索** | rank_bm25 | BM25 算法 |
| **混合检索融合** | LangChain EnsembleRetriever | 加权融合 |
| **重排器** | BGE-Reranker（预留） | Top-K 精排 |
| **多模型分工** | 三档（轻量/中量/重量） | 按复杂度调用，成本降 80%+ |
| **Agent 架构** | 主控 + 子 Agent | 上下文隔离、分模型、可测试 |
| **上下文优化** | Prompt 精简+压缩+缓存+拼接顺序 | 多策略组合节省 60%+ |
| **成本可观测** | llm_call_logs 表 | 开发者侧记录调优 |
| **JWT 库** | python-jose | 认证 Token |
| **密码哈希** | bcrypt | 密码安全 |
| **部署** | Docker Compose | 后端 + Nginx 前端两个容器 |
| **CI/CD** | GitHub Actions | 自动化测试与构建 |
| **施工日志** | docs/dev-log.md | 开发进度记录 |

### 1.2 选型原则

1. **大模型生态优先**：本项目重度依赖 LLM，Python + LangChain 生态最强。
2. **开发效率优先**：MVP 阶段效率 > 极致性能。
3. **面试讲解加分**：技术选型能清晰展示取舍思考。
4. **平滑升级路径**：MVP 选轻量方案，但预留向生产级迁移的接口。
5. **组件可插拔**：工具模块遵循开闭原则，新增不改旧。
6. **中文友好**：文档、社区、注释均以中文为主。
7. **成本可控**：多模型分工、上下文压缩、缓存复用，避免大模型调用成本失控。

---

## 2. 后端技术栈

### 2.1 选型决策

**Python 3.11 + FastAPI + Pydantic v2 + 全异步 + RESTful/OpenAPI**

### 2.2 选型理由

#### 为什么选 Python + FastAPI

| 维度 | 评估 |
|:----- |:----- |
| 大模型生态 | ⭐⭐⭐⭐⭐ LangChain/LlamaIndex 原生 Python，OpenAI SDK 优先 Python |
| 开发效率 | ⭐⭐⭐⭐⭐ 自动文档、类型提示、Pydantic 校验开箱即用 |
| 类型安全 | ⭐⭐⭐⭐ Pydantic v2 提供运行时校验 |
| 性能（10 并发足够） | ⭐⭐⭐⭐ Uvicorn + asyncio 足够 |
| 简历辨识度 | ⭐⭐⭐⭐⭐ 面试官一眼看懂，与 AI 应用方向契合 |

#### 对比淘汰方案

- **Node.js + NestJS**：AI 生态弱于 Python，前后端同语言优势在本项目（前后端分离）不突出。
- **Go + Gin**：性能最强但 AI 生态薄弱，需自己封装大模型调用，开发成本高。

### 2.3 全异步的必要性

- 大模型流式输出必须用 async（否则阻塞事件循环）。
- SSE 长连接需要异步处理。
- SQLAlchemy 2.0 异步与 FastAPI 一致，避免同步阻塞线程池。

### 2.4 RESTful + OpenAPI 风格

- 资源清晰：`/projects`、`/purchase-orders`、`/quotes` 等。
- 动作端点用 POST + 动词路径：`/purchase-orders/{id}/submit`、`/purchase-orders/{id}/approve`。
- OpenAPI 文档自动生成（FastAPI 内置），便于前端联调与面试演示。

### 2.5 统一响应格式

```python
# 所有 API 返回统一格式
{
    "code": 0,         # 0 成功，非 0 失败
    "msg": "ok",       # 消息描述
    "data": {...}      # 业务数据，失败时为 null
}
```

### 2.6 大模型调用策略（遵循想法.txt 约束）

- **能不调用大模型就不调用**：纯数据库 CRUD、状态机变更、权限校验等用确定性代码。
- **必须调用大模型的场景**：清单解析、报价解析、对话回答、比价建议生成、知识库检索。
- **降级策略**：大模型不可用时降级为模板方案，响应中标注 `source: "template"`。

---

## 3. 前端技术栈

### 3.1 选型决策

**Vue 3 + Vite + Pinia + Axios + Element Plus + ECharts + markdown-it**

### 3.2 选型理由

#### 为什么选 Vue 3

| 维度 | 评估 |
|:----- |:----- |
| 对话 UI 流式渲染 | ⭐⭐⭐⭐ 组合式 API + 响应式数据，易实现增量渲染 |
| 中文资料与社区 | ⭐⭐⭐⭐⭐ 国内第一，文档最完善 |
| 组件库丰富度 | ⭐⭐⭐⭐⭐ Element Plus / Naive UI 成熟 |
| 后续多端复用 | ⭐⭐⭐⭐⭐ uni-app / Taro 可扩展小程序 |
| 学习曲线 | ⭐⭐⭐⭐⭐ HTML/CSS/JS 基础即可上手 |

#### 对比淘汰方案

- **React 18**：生态最丰富但中文资料不如 Vue、JSX 学习成本高、与想法.txt 倾向不符。
- **Svelte 5**：包体积小但生态薄弱、企业级组件库少。

### 3.3 关键库选型

| 库 | 用途 | 选型理由 |
|:--- |:----- |:-------- |
| Vite | 构建工具 | Vue 官方推荐、热更新极快、配置简单 |
| Pinia | 状态管理 | Vue 3 官方推荐、TS 支持好、API 简洁 |
| Axios | HTTP 客户端 | 拦截器机制成熟、SSE 支持需配合 fetch |
| Element Plus | UI 组件库 | 中文文档最好、表格表单丰富、与后台管理场景契合 |
| ECharts | 图表库 | 中文文档好、支持柱状图/雷达图/折线图全场景 |
| markdown-it | Markdown 渲染 | 轻量、安全（防 XSS）、插件化、对话流式首选 |

### 3.4 SSE 流式渲染实现

前端用原生 `fetch` + `ReadableStream` 处理 SSE（Axios 对流式支持不佳），对话消息增量渲染：

```javascript
// 伪代码：SSE 流式接收
const response = await fetch('/api/chat/stream', { method: 'POST', body: ... });
const reader = response.body.getReader();
while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    // 增量追加到当前消息
    appendToCurrentMessage(decode(value));
}
```

---

## 4. 数据库与存储

### 4.1 选型决策

**SQLite + SQLAlchemy 2.0（异步）+ Alembic + 本地文件系统**

### 4.2 选型理由

#### 为什么选 SQLite

| 维度 | 评估 |
|:----- |:----- |
| MVP 部署难度 | ⭐⭐⭐⭐⭐ 零部署、单文件、备份即复制 |
| 10 并发用户足够 | ⭐⭐⭐⭐ WAL 模式下并发读无限制、单写足够 |
| 面试讲解加分 | ⭐⭐⭐⭐ 讲清取舍比直接上 PostgreSQL 更显工程思维 |

#### SQLite 配置要点

- 启用 **WAL 模式**：`PRAGMA journal_mode=WAL`，提升并发读写能力。
- 启用 **外键约束**：`PRAGMA foreign_keys=ON`。
- 连接池：用 `aiosqlite` 异步驱动，连接数控制在 5-10。

#### 为什么选 SQLAlchemy 2.0 异步

- 跨数据库抽象：后续可平滑迁移到 PostgreSQL（仅改驱动与连接串）。
- 类型提示与 Pydantic 集成好。
- Alembic 提供专业迁移能力。

### 4.3 迁移工具

**Alembic**：SQLAlchemy 官方配套，版本控制 schema。

工作流：
1. 修改 SQLAlchemy 模型
2. `alembic revision --autogenerate -m "描述"` 生成迁移脚本
3. 人工 review 脚本
4. `alembic upgrade head` 应用迁移

### 4.4 文件存储

**本地文件系统**（MVP）：
- 路径规范：`uploads/{team_id}/{type}/{yyyy/mm}/{uuid}{ext}`
- type 分类：`list`（清单）、`quote`（报价）、`knowledge`（知识库文件）、`inquiry`（询价单）
- 数据库只存路径，不存二进制。
- **预留扩展点**：抽象 `Storage` 接口，后续可替换为阿里云 OSS 实现而不改业务代码。

### 4.5 升级路径

当数据量增长或并发压力增大时：
1. 数据库：SQLite → PostgreSQL（SQLAlchemy 抽象层，仅改驱动与连接串）
2. 文件存储：本地 → 阿里云 OSS（Storage 接口替换实现）

---

## 5. 大模型集成层

### 5.1 选型决策

**LangChain + SSE + Pydantic 结构化输出 + 嵌入同供应商**

### 5.2 选型理由

#### 为什么选 LangChain

| 能力 | LangChain | LlamaIndex | 原生 SDK |
|:----- |:---------:|:----------:|:--------:|
| 多工具调度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| RAG 能力 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| Pydantic 输出 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 流式输出 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 工具注册扩展 | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

本项目"多工具调度 + RAG + 对话"三者并重，LangChain 是唯一全覆盖方案。

#### LangChain 关键能力使用

1. **Tool 抽象**：每个功能（清单解析、询价生成、比价等）封装为 Tool，遵循开闭原则。
2. **Agent 调度**：根据用户意图路由到对应 Tool。
3. **Memory 管理**：短期对话记忆用 `ConversationBufferWindowMemory`。
4. **Retriever**：RAG 检索器，对接 Chroma 向量库。
5. **with_structured_output**：清单/报价解析直接得 Pydantic 对象。

### 5.3 流式协议

**SSE（Server-Sent Events）**：
- HTTP 长连接推送，实现简单。
- 静态托管友好，无需特殊配置。
- 浏览器原生 `EventSource` 或 `fetch + ReadableStream` 接收。

FastAPI 端用 `StreamingResponse` 实现 SSE。

### 5.4 结构化输出

**Pydantic + LangChain with_structured_output**：

```python
from pydantic import BaseModel, Field

class PurchaseItem(BaseModel):
    species: str = Field(description="苗木品种中文名称")
    spec: str = Field(description="规格，如'胸径12cm'")
    quantity: float = Field(description="数量")
    unit: str = Field(description="单位，如'株'")

class PurchaseList(BaseModel):
    items: list[PurchaseItem]
    confidence: float = Field(description="整体置信度，0-1")

# LangChain 调用
structured_llm = llm.with_structured_output(PurchaseList)
result = structured_llm.invoke("香樟胸径12cm×30, 桂花8cm×20")
# result 是 PurchaseList 对象，可直接用
```

### 5.5 嵌入模型

**走 OpenAI 兼容端点，默认独立于主模型供应商**：
- 嵌入模型统一通过 OpenAI 兼容端点配置（`EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` / `EMBEDDING_MODEL`）。
- 默认候选：`text-embedding-3-small`（通用，多供应商可用）或 `bge-m3`（中文效果好）。
- 若主模型供应商也提供兼容的 embedding 接口，可优先同源（便于计费与排障）；否则嵌入单独配置，如经聚合中转站提供。

### 5.6 大模型供应商配置

- MVP 阶段由开发者在服务端环境变量配置（`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`EMBEDDING_MODEL`）。
- 支持 OpenAI 兼容接口，可切换 DeepSeek/通义/智谱等。
- **预留扩展点**：后续可开放用户自助配置（在设置页填自己的 Key）。

---

## 6. 混合检索方案（核心架构）

### 6.1 选型决策

**LangChain EnsembleRetriever + rank_bm25 + Chroma + BGE-Reranker（预留）**

### 6.2 架构图

```
用户查询
   ↓
   ├─ BM25Retriever（rank_bm25）  → 关键词匹配结果（权重 w1=0.4）
   ├─ Chroma 向量检索               → 语义匹配结果（权重 w2=0.6）
   ↓
EnsembleRetriever 加权融合（RRF 算法）
   ↓
（可选）BGE-Reranker 重排 Top-20
   ↓
最终 Top-K 结果 → 大模型生成回答
```

### 6.3 核心概念解释

#### BM25（关键词检索）
基于词频（TF）与逆文档频率（IDF）的检索算法。一个词在当前文档出现多次但全库少见 → 权重高；常见词（"的"、"是"）→ 权重低。比 LIKE 智能得多。

#### 向量检索（语义检索）
把文本转成向量（如 1536 维数组），查询时计算向量间余弦相似度。能理解"樟树"≈"香樟"的同义关系。

#### EnsembleRetriever（融合检索器）
LangChain 内置组件，传入多个 retriever 与权重，自动融合。底层用 RRF（Reciprocal Rank Fusion，倒数排名融合）算法——把每路结果的排名取倒数后相加，简单有效。

#### Reranker（重排器）
对初步检索的 Top-20 用 cross-encoder 重新打分排序，提升 Top-K 精度。比向量检索更准但更慢，所以只对少量候选重排。

### 6.4 权重默认配置

- BM25 权重：0.4
- 向量检索权重：0.6
- 理由：语义匹配为主（解决同义词/口语化），关键词兜底精确匹配（如规格"胸径12cm"）。
- 权重可在团队设置中调整。

### 6.5 Reranker 策略

- MVP 阶段先不启用 Reranker，靠 EnsembleRetriever 融合。
- 预留 BGE-Reranker 接入点：当召回不准或数据量增长后启用。
- BGE-Reranker 为智源开源，中文场景效果好，本地跑免费。

### 6.6 检索场景应用

| 场景 | 检索对象 | 融合策略 |
|:----- |:----- |:----- |
| 行业认知库查询 | 苗木品种/规格术语 | 向量权重 0.7（语义为主） |
| 历史价格检索 | 采购记录/成交价 | BM25 权重 0.5（规格精确匹配重要） |
| 供应商信息查询 | 供应商记录 | BM25 权重 0.6（名称精确匹配） |

### 6.7 中文分词

- rank_bm25 内置简单分词，但中文需 jieba 增强分词。
- 维护自定义词典：苗木品种名（香樟、桂花、银杏等），提升分词准确度。

---

## 7. 成本优化与多模型多 Agent 架构

### 7.1 设计目标

- **分层调用**：按功能复杂度调用不同价位模型，避免"杀鸡用牛刀"。
- **Agent 分工**：各功能由专用 Agent 执行，上下文隔离、Prompt 精简、可独立测试。
- **上下文优化**：Prompt 精炼、压缩有阈值、拼接有序、缓存复用。
- **成本可观测**：开发者侧记录每次调用，便于对比与调优。

### 7.2 多模型三档分工

#### 模型档位定义

| 档位 | 适用任务 | 代表模型（OpenAI 兼容） | 单价参考 |
|:----- |:----- |:----- |:----- |
| **轻量档** | 结构化提取、意图分类、模板填充 | gpt-4o-mini / DeepSeek-V3 / Qwen-Plus | ¥0.5-2/百万token |
| **中量档** | 对话回复、检索回答、总结 | gpt-4o / DeepSeek-V3 / Qwen-Plus | ¥2-10/百万token |
| **重量档** | 多维推理、比价建议、复杂分析 | gpt-4o / Claude 3.5 Sonnet / DeepSeek-R1 | ¥10-40/百万token |
| **嵌入档** | 向量嵌入 | text-embedding-3-small / bge-m3 | ¥0.1-1/百万token |

> **说明**：上表"代表模型"及下方配置示例中的模型名均为**价位示意**，仅用于说明各档位成本量级与能力差异；具体可用型号以实际 API 供应商/聚合中转站为准，配置时以服务端环境变量实际值为准，且应与当下最新可用模型对应。

**JEV（TypeSafe System One）**：意图路由的主模型，不属于三档聊天模型，也不兼容
OpenAI `/v1/chat/completions`；只能调用 `/v1/systemone` 并返回 choice/概率/置信度。
通过 `LLMFactory.get_jev()` 获取，失败时自动降级到规则 + 轻量档。

#### 各功能模型分配

| 功能 | 模型档位 | 理由 |
|:----- |:-------- |:----- |
| 清单解析（结构化） | 轻量档 | 模式固定，简单提取 |
| 报价单解析（结构化） | 轻量档 | 同上 |
| 询价单生成 | 轻量档 | 模板填充为主 |
| 知识库检索回答 | 中量档 | 需理解检索结果组织语言 |
| 比价建议生成 | 重量档 | 需多维度推理 |
| 对话主回复 | 中量档 | 日常对话 |
| 历史趋势分析 | 中量档 | 需解读数据 |
| Agent 路由/意图识别 | 轻量档 | 分类任务 |
| 嵌入向量 | 嵌入档 | 专用模型 |

#### 配置方式

环境变量按档位配置，支持运行时切换：

```env
# 轻量档（结构化提取、路由分类）
LLM_LIGHT_MODEL=deepseek-v3
LLM_LIGHT_BASE_URL=https://api.deepseek.com/v1
LLM_LIGHT_API_KEY=sk-xxx

# 中量档（对话、检索回答）
LLM_MEDIUM_MODEL=gpt-4o
LLM_MEDIUM_BASE_URL=https://api.openai.com/v1
LLM_MEDIUM_API_KEY=sk-xxx

# 重量档（复杂推理）
LLM_HEAVY_MODEL=claude-3-5-sonnet
LLM_HEAVY_BASE_URL=https://api.anthropic.com/v1
LLM_HEAVY_API_KEY=sk-xxx

# 嵌入档
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=sk-xxx
```

**成本预估**（日均 100 次调用）：
- 全用重量档：约 ¥30-50/天
- 三档分工后：约 ¥3-8/天（节省 80%+）

### 7.3 主 + 子 Agent 架构（方案 B）

#### 架构图

```
用户输入
   ↓
[主控 Agent / Router]
   ├─ 意图识别（轻量模型分类）
   ├─ 路由到对应子 Agent
   ↓
[清单解析 Agent] [询价单 Agent] [比价 Agent] [知识库 Agent] [对话 Agent]
   每个 Agent 自带：
   - 专用 Prompt（精简）
   - 专用模型（按需）
   - 专用工具（Pydantic schema）
   - 专用上下文（仅相关数据）
```

#### Agent 职责定义

| Agent | 模型档位 | 输入 | 输出 | 工具 |
|:----- |:----- |:----- |:----- |:----- |
| Router（主控） | 轻量 | 用户文本 | 意图标签 + 路由目标 | 无 |
| 清单解析 Agent | 轻量 | 文件/文本 | PurchaseList Pydantic 对象 | 文件读取 |
| 询价单 Agent | 轻量 | 采购清单 + 模板 | 询价单文件路径 | 模板引擎 |
| 比价 Agent | 重量 | 多报价 + 历史评分 | 比价报告 + 建议 | 比价计算（确定性代码） |
| 知识库 Agent | 中量 | 用户问题 + 检索结果 | 自然语言回答 | EnsembleRetriever |
| 对话 Agent | 中量 | 用户消息 + 对话历史 | 流式回复 | 无（纯对话） |

#### 为什么选主+子 Agent（而非单 Agent + 多 Tool）

| 维度 | 主+子 Agent | 单 Agent+多Tool |
|:----- |:---------- |:--------------- |
| 上下文隔离 | ⭐⭐⭐⭐⭐ 各 Agent 只看相关数据 | ⭐⭐ 上下文臃肿 |
| 分模型调用 | ⭐⭐⭐⭐⭐ 各 Agent 用不同模型 | ⭐ 难以分模型 |
| 可测试性 | ⭐⭐⭐⭐⭐ Agent 独立测试 | ⭐⭐ 耦合难测 |
| Token 成本 | ⭐⭐⭐⭐⭐ 上下文精简 | ⭐⭐ 每次带全量工具描述 |
| 实现复杂度 | ⭐⭐⭐ 中等 | ⭐⭐⭐⭐ 简单 |

### 7.4 Prompt 精简规范

#### 五大原则

1. **角色定义简短**：只说"你是XX，负责XX"，不写冗长背景。
2. **规则用编号要点**：而非段落描述。
3. **示例最少化**：只在歧义时给 1 个示例。
4. **输出格式用 schema**：用 Pydantic schema 替代自然语言描述格式。
5. **动态拼接**：只拼接当前任务相关上下文，不塞全量。

#### 对比示例

**冗长 Prompt（不推荐，约 700 token）**：
```
你是一个园林采购清单解析助手，负责从用户输入的文本中提取苗木采购清单。
园林采购中常见的苗木品种包括香樟、桂花、银杏等，规格通常用胸径表示...
（500字背景介绍）
请将以下内容解析为JSON格式，字段包括品种、规格、数量、单位...
（200字格式描述）
```

**精简 Prompt（推荐，约 80 token）**：
```
提取苗木清单为JSON。规则：
1. species 用中文标准名
2. spec 含数值+单位
3. quantity 为数字
{{input}}
```

Token 减少 80%+，效果相同。

### 7.5 上下文压缩与缓存策略

#### 策略 A：对话记忆压缩（阈值控制）

**机制**：
- 保留最近 N 轮原文（默认 N=6）。
- 超过阈值时，将早期对话用轻量模型生成摘要。
- 用 LangChain `ConversationSummaryBufferMemory`（max_token_limit 参数控制阈值）。

**关键优化（用户提出）**：
- **压缩阈值依模型能力而定**：能力强的模型可用更长窗口、更少压缩；能力弱的频繁压缩。
- **避免过度频繁压缩**：每次压缩会破坏 Prompt Cache（缓存键变化），反而增加成本。建议阈值设为"窗口接近模型上下文上限的 70%"再触发压缩。
- **压缩时用轻量模型**：摘要任务用轻量档模型，不消耗重量档配额。

#### 策略 B：Prompt 缓存（供应商级）

**机制**：
- 部分供应商（Anthropic Prompt Cache、DeepSeek Context Cache）支持不变段缓存。
- 命中后该段不计费或计费降至 10%。
- 适合：系统指令、知识库文档、模板等不变内容。

**使用方式**：
- LangChain 已封装 `cache` 参数，标记可缓存段。
- 调用时把系统指令、知识库文档放在消息序列开头并标记 cache。

#### 策略 C：检索结果裁剪

**机制**：
- RAG 检索 Top-20，但只把 Top-5 精华喂给大模型。
- 长文档只取相关段落（按句子/段落切分后用 BM25 选段）而非全文。
- 检索结果按相关度排序后裁剪，保留高分包。

#### 策略 D：本地缓存

**机制**：
- 相同请求结果缓存到 SQLite（`llm_cache` 表，字段 `prompt_hash, response, model, created_at`）。
- 知识库查询类（如"香樟规格定义"）命中直接返回，零成本。
- 缓存键 = `(model, system_prompt_hash, user_input_hash)`。
- TTL：知识库类永久，对话类不缓存。

### 7.6 上下文拼接顺序规范（关键优化）

**用户提出的关键原则**：不易变的放上面、易变的放尾部。

**原因**：
- 大模型对消息序列开头部分容易命中 Prompt Cache。
- 尾部内容变化不影响开头缓存。
- 大模型对最近上下文关注度更高，动态数据放尾部利于准确理解。

**标准拼接顺序（从上到下）**：

```
[1] System Prompt（固定，最稳定，命中缓存）
    - 角色定义、规则、输出格式说明
[2] 知识库文档（半静态，定期更新，命中缓存）
    - 行业认知库相关内容
    - 团队偏好规则
[3] 检索结果（每次可能不同，但同会话内可复用）
    - RAG Top-5 结果
[4] 对话历史摘要（按阈值压缩）
    - 早期对话摘要
[5] 最近 N 轮原文（动态变化）
[6] 当前用户输入（最易变，放最后）
```

**拼接实现**：

```python
# 伪代码：上下文拼接
def build_context(system_prompt, knowledge_docs, retrieved, history_summary,
                  recent_turns, current_input):
    return [
        SystemMessage(content=system_prompt),                    # [1] 固定，可缓存
        SystemMessage(content=knowledge_docs, cache=True),       # [2] 半静态，标记缓存
        HumanMessage(content=f"参考知识：{retrieved}"),            # [3] 检索结果
        HumanMessage(content=f"历史摘要：{history_summary}"),      # [4] 压缩摘要
        *[msg for turn in recent_turns for msg in turn],          # [5] 最近N轮
        HumanMessage(content=current_input),                     # [6] 当前输入
    ]
```

### 7.7 成本可观测（开发者侧）

**机制**：
- 每次调用记录到 `llm_call_logs` 表（仅开发者可见，不给用户展示）。
- 字段：`agent_name, model, input_tokens, output_tokens, cost, latency_ms, cache_hit, created_at`。
- 用途：开发者对比不同模型/Agent 的成本与效果，指导调优。

**数据模型**：

```sql
CREATE TABLE llm_call_logs (
    id INTEGER PRIMARY KEY,
    agent_name TEXT,          -- Agent 名称（如 router/list_parser/compare）
    model TEXT,               -- 调用的模型
    input_tokens INTEGER,     -- 输入 token 数
    output_tokens INTEGER,    -- 输出 token 数
    cost REAL,                -- 本次调用成本（元）
    latency_ms INTEGER,       -- 耗时毫秒
    cache_hit BOOLEAN,        -- 是否命中缓存
    session_id TEXT,          -- 关联会话
    created_at DATETIME
);
```

**查询场景**：
- 按模型汇总成本：哪个模型花钱最多？
- 按 Agent 汇总：哪个 Agent 调用最频繁？
- 按时段趋势：成本是涨是降？
- 缓存命中率：Prompt Cache 是否生效？

### 7.8 成本优化效果预估

| 优化措施 | 节省比例 |
|:----- |:----- |
| 三档模型分工 | 节省 80%+（相比全用重量档） |
| Prompt 精简 | 节省 50-80%（单次 token 数） |
| 对话记忆压缩 | 长会话节省 60%+ |
| Prompt 缓存命中 | 缓存段节省 90% |
| 检索结果裁剪 | 节省 75%（Top-20→Top-5） |
| 本地缓存命中 | 命中后零成本 |

**综合预估**：日均 100 次调用，全优化后成本约 ¥2-5/天。

---

## 8. 认证与安全

### 8.1 选型决策

**python-jose（JWT）+ bcrypt（密码哈希）**

### 8.2 JWT 认证流程

1. 用户登录（用户名+密码）→ 校验密码 → 生成 JWT。
2. JWT 载荷：`{user_id, team_id, role, exp}`。
3. 前端存 localStorage，每次请求放 `Authorization: Bearer <token>`。
4. 后端 FastAPI 依赖注入校验 JWT，提取用户与团队信息。
5. Token 过期 → 前端跳登录页。

### 8.3 密码哈希

- **bcrypt**：直接调用原生哈希接口，自带盐值；避免 passlib 与新版本 bcrypt 的兼容问题。
- 即使数据库泄露，密码也无法逆向。
- 未来可迁移到 argon2，需要为存量哈希保留登录兼容。

### 8.4 团队数据隔离

- 所有业务表通过 `team_id` 或父实体实现隔离。
- **数据访问层强制拦截**：查询必须带 `team_id` 过滤，禁止业务层裸 SQL 绕过。
- 实现方式：SQLAlchemy 的 `with_loader_criteria` 或自定义 Session 工厂。

### 8.5 审计日志

- 关键操作（下单/审批/删除/修改采购单）记录到 `audit_logs` 表。
- 字段：`team_id, user_id, action, target_type, target_id, diff_json, created_at`。
- 保留至少 90 天。

### 8.6 注入防护

- **SQL 注入**：SQLAlchemy 参数化查询，禁止字符串拼接。
- **Prompt 注入**：用户输入作为变量传入 Prompt，用 LangChain 的 `SystemMessage` 隔离系统指令。

---

## 9. 部署与运维

### 9.1 选型决策

**Docker Compose（backend + frontend/Nginx 两个容器）**

### 9.2 运行方式

- backend：FastAPI + 嵌入式 Chroma + SQLite；启动前执行 Alembic，默认单 worker。
- frontend：Vite 构建产物由 Nginx 托管，并把 `/api` 反代到 backend。
- 数据：命名卷 `backend_data`（SQLite 与上传文件）与 `backend_chroma`（向量库）。
- 对外端口：默认 8090，可用 `APP_PORT` 覆盖；backend 仅在内网暴露 8000。

### 9.3 环境变量清单

```env
# 数据库
DATABASE_URL=sqlite+aiosqlite:///./data/app.db

# 大模型（三档分工，开发者服务端预置）
LLM_LIGHT_MODEL=deepseek-v3
LLM_LIGHT_BASE_URL=https://api.deepseek.com/v1
LLM_LIGHT_API_KEY=sk-xxx

LLM_MEDIUM_MODEL=gpt-4o
LLM_MEDIUM_BASE_URL=https://api.openai.com/v1
LLM_MEDIUM_API_KEY=sk-xxx

LLM_HEAVY_MODEL=claude-3-5-sonnet
LLM_HEAVY_BASE_URL=https://api.anthropic.com/v1
LLM_HEAVY_API_KEY=sk-xxx

EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=sk-xxx

# JEV 意图路由（非 OpenAI 兼容；Key 为空时自动降级）
JEV_ENABLED=true
JEV_API_KEY=
JEV_ENDPOINT=https://ai-gateway.edgeone.link/v1/systemone
JEV_MODEL=@makers/jev
JEV_CONCURRENCY=24
JEV_TIMEOUT_S=10
JEV_LOW_CONFIDENCE_THRESHOLD=0.60
ROUTE_CONFIRM_TTL_MINUTES=30

# JWT
JWT_SECRET=your-secret-key
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# 文件存储
UPLOAD_DIR=./data/uploads
MAX_FILE_SIZE_MB=5

# 应用
APP_ENV=production
LOG_LEVEL=INFO
```

### 9.4 部署流程

1. 本地开发 → GitHub 推送
2. 使用者 clone 仓库 → 复制 `.env.example` 为 `backend/.env` 并填写配置
3. `docker compose up -d --build` → 访问 `http://localhost:8090`
4. 停止 `docker compose down`；清空数据 `docker compose down -v`

---

## 10. 工程化配套

### 10.1 GitHub Actions CI/CD

- **触发**：push 到 main 分支、PR 提交。
- **流水线**：
  1. 代码检出
  2. 安装依赖（pip + npm ci）
  3. 后端测试（pytest + 覆盖率）
  4. 前端构建（vite build）
  5. 前端测试（vitest）

### 10.2 施工日志 `docs/dev-log.md`

记录每个模块开发进度、决策、坑点，与 git commit 对应。

格式：
```markdown
## [日期] 模块名

### 完成内容
- ...

### 决策记录
- ...

### 遇到的坑
- ...

### 关联 commit
- abc123: 描述
```

### 10.3 代码规范

- Python：PEP8 + ruff 格式化、type hints、函数 ≤ 50 行。
- JavaScript/TypeScript：Prettier + ESLint、单引号、尾随逗号。
- 中文注释与文档（遵循用户偏好：参数出现时需在注释中说明其作用）。
- 模块间通信使用 Pydantic 模型，禁止裸 dict 传递。
- 工具模块遵循开闭原则：新增工具只需注册，不改现有代码。

### 10.4 测试要求

- 后端：pytest + pytest-asyncio + pytest-cov
- 前端：Vitest + Vue Test Utils
- 覆盖率：核心模块 100%，整体 ≥ 80%
- 命令：`pytest tests/ -v`、`cd frontend && npm test`

---

## 11. 选型决策汇总表

| 层次 | 选型 | 关键理由 |
|:----- |:----- |:----- |
| 后端语言 | Python 3.11 | 大模型生态最强 |
| 后端框架 | FastAPI + Pydantic v2 | 自动文档、类型校验、异步原生 |
| 后端风格 | 全异步 | 流式输出必需 |
| API 风格 | RESTful + OpenAPI | 清晰规范、自动文档 |
| 数据库 | SQLite | 零部署、MVP 足够 |
| ORM | SQLAlchemy 2.0 异步 | 跨库抽象、平滑迁移 |
| 迁移工具 | Alembic | 专业 schema 版本管理 |
| 文件存储 | 本地文件系统 | MVP 简单、预留 OSS 接口 |
| 前端框架 | Vue 3 + Vite + Pinia | 中文社区强、后续可扩展小程序 |
| HTTP 客户端 | Axios | 拦截器成熟 |
| UI 组件库 | Element Plus | 中文文档好、后台管理场景契合 |
| 图表库 | ECharts | 中文文档好、全场景支持 |
| Markdown 渲染 | markdown-it | 轻量、安全、流式首选 |
| 大模型集成层 | LangChain | 多工具调度+RAG+Memory 全覆盖 |
| 流式协议 | SSE | 实现简单、代理友好 |
| 结构化输出 | Pydantic + with_structured_output | 直接得对象、类型安全 |
| 嵌入模型 | 与大模型同供应商 | 计费统一、故障排查方便 |
| 向量库 | Chroma | 嵌入式部署、LangChain 集成好 |
| 关键词检索 | rank_bm25 | 轻量、算法成熟 |
| 混合检索融合 | LangChain EnsembleRetriever | 加权融合内置、RRF 算法 |
| 重排器 | BGE-Reranker（预留） | 中文场景好、本地免费 |
| **多模型分工** | **三档（轻量/中量/重量）** | **按功能复杂度调用，成本降 80%+** |
| **Agent 架构** | **主控+子 Agent** | **上下文隔离、分模型、可测试** |
| **上下文优化** | **Prompt 精简 + 压缩 + 缓存 + 拼接顺序** | **多策略组合，综合节省 60%+** |
| **成本可观测** | **llm_call_logs 表** | **开发者侧记录，便于调优** |
| JWT 库 | python-jose | FastAPI 官方推荐 |
| 密码哈希 | bcrypt | 跨平台稳定、无中间层兼容问题 |
| 部署 | Docker Compose | 两容器一键启停、演示复现性强 |
| CI/CD | GitHub Actions | 与私密仓库一致、免费额度够 |
| 施工日志 | docs/dev-log.md | 与 commit 对应、面试讲解 |

---

## 12. 扩展点与升级路径

| 当前（MVP） | 升级目标 | 升级方式 |
|:----------- |:--------- |:-------- |
| SQLite | PostgreSQL | 改 SQLAlchemy 驱动与连接串 |
| 本地文件存储 | 阿里云 OSS | 替换 Storage 接口实现 |
| Chroma 嵌入式 | Qdrant 生产级 | 替换 LangChain VectorStore |
| 无 Reranker | BGE-Reranker | 接入 EnsembleRetriever 后置 |
| 开发者配置大模型 | 用户自助配置 | 新增设置页与用户配置表 |
| 单团队 | 多团队多角色 | 数据模型已预留多对多 |
| Web 单端 | 小程序/IM | Taro/uni-app 复用业务逻辑 |
| 询价单仅下载 | 邮件/IM 自动发送 | 新增通知服务模块 |
| 全部采购员 | 供应商在线填报 | 新增供应商侧轻量入口 |
| 主+子 Agent | LangGraph 状态图编排 | 复杂工作流时升级 |

---


---

**施工说明**：本版本移除了需要项目方后续确认的选型/运维事项；已确认的技术选型、成本策略、部署方案和升级路径保持原文。
