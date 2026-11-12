# SDD — LLM 工厂模块（llm_factory）

> **依据**：system-design.md §2.2.13，tech-stack.md §7.2，CLAUDE.md §6.2
> **代码位置**：`backend/app/services/llm_factory.py`

---

## 1. 功能描述

按档位（light / medium / heavy / embedding）创建并缓存 LangChain LLM 实例。
统一通过 `ChatOpenAI(base_url=..., api_key=...)` 访问 OpenAI 兼容端点，支持 DeepSeek / 通义 / 智谱 / Anthropic 等任意兼容供应商。
实例缓存在类变量 `_instances` 中，进程生命周期内复用，不重复实例化。

另提供 `get_jev()`：JEV（TypeSafe System One）是类型化判定服务，不属于聊天档位，
协议为 `/v1/systemone`，不能走 OpenAI 兼容接口；同样由本工厂缓存并提供给 RouterAgent。

---

## 2. 接口签名

```python
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings

class LLMFactory:
    _instances: dict[str, BaseChatModel | Embeddings] = {}

    @classmethod
    def get_light(cls) -> BaseChatModel:
        """返回轻量档 LLM 实例（结构化提取、路由分类、摘要压缩）。
        环境变量：LLM_LIGHT_MODEL / LLM_LIGHT_BASE_URL / LLM_LIGHT_API_KEY
        """

    @classmethod
    def get_medium(cls) -> BaseChatModel:
        """返回中量档 LLM 实例（对话、检索回答、趋势分析）。
        环境变量：LLM_MEDIUM_MODEL / LLM_MEDIUM_BASE_URL / LLM_MEDIUM_API_KEY
        """

    @classmethod
    def get_heavy(cls) -> BaseChatModel:
        """返回重量档 LLM 实例（比价建议、复杂推理）。
        环境变量：LLM_HEAVY_MODEL / LLM_HEAVY_BASE_URL / LLM_HEAVY_API_KEY
        """

    @classmethod
    def get_embedding(cls) -> Embeddings:
        """返回嵌入模型实例（向量化，供 Chroma 使用）。
        环境变量：EMBEDDING_MODEL / EMBEDDING_BASE_URL / EMBEDDING_API_KEY
        """

    @classmethod
    def get_jev(cls) -> "JevClient":
        """返回 JEV 判定客户端（意图路由）。
        环境变量：JEV_API_KEY（或 MAKERS_MODELS_KEY）/ JEV_ENDPOINT / JEV_MODEL
        """

    @classmethod
    def reset(cls) -> None:
        """清空缓存，用于测试隔离。"""
```

### Pydantic 输入/输出模型

LLMFactory 本身不定义业务 I/O 模型；调用方（Agent）使用 `llm.with_structured_output(SomeSchema)` 获得 Pydantic 对象。

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `langchain-openai` | `ChatOpenAI`, `OpenAIEmbeddings` |
| `langchain-anthropic`（可选） | 若 Anthropic 端点工具调用有兼容性问题时使用 `ChatAnthropic` |
| `app.core.config.settings` | 从环境变量读取三档模型配置 |
| `app.core.exceptions.ConfigError` | 配置缺失时抛出 |
| `app.services.jev_client.JevClient` | JEV 类型化判定客户端（`get_jev()`） |

### Anthropic 兼容说明
- 默认用 `ChatOpenAI(base_url="https://api.anthropic.com/v1")` 调用 Anthropic。
- 若工具调用/流式遇到兼容性问题，改用 `langchain_anthropic.ChatAnthropic`（在 llm_factory.py 内部切换，调用方无感）。

---

## 4. 异常处理

| 异常 | 触发条件 | 处理策略 |
|:---- |:-------- |:-------- |
| `ConfigError` | 对应环境变量未设置或为空 | 工厂方法启动即检查，抛出后由 lifespan 捕获，服务拒绝启动 |
| `LLMUnavailableError` | 网络不通 / API Key 无效（运行时） | 由调用方（Agent）捕获，执行降级策略（返回 `source:"template"` 或提示用户） |

降级策略不在工厂层实现，工厂只负责创建实例，由 Agent 层 try/except 处理。
