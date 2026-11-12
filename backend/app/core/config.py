"""应用配置，从环境变量加载，依据 .env.example"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 数据库
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/app.db"
    # 连接池（多 worker 部署时每 worker 各持一个池，总连接 = 值 × worker 数）
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    # 轻量档 LLM
    LLM_LIGHT_MODEL: str = "deepseek-v3"
    LLM_LIGHT_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_LIGHT_API_KEY: str = ""

    # 中量档 LLM
    LLM_MEDIUM_MODEL: str = "gpt-4o"
    LLM_MEDIUM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MEDIUM_API_KEY: str = ""

    # 重量档 LLM（需 OpenAI 兼容接口，不能填 Anthropic 原生地址）
    LLM_HEAVY_MODEL: str = "your-heavy-model"
    LLM_HEAVY_BASE_URL: str = "https://your-openai-compatible-provider.example/v1"
    LLM_HEAVY_API_KEY: str = ""

    # 嵌入模型
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_BASE_URL: str = "https://api.openai.com/v1"
    EMBEDDING_API_KEY: str = ""

    # 重排序模型（RAG 二阶段精排，Cohere 风格 /rerank 接口）
    RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"
    RERANK_BASE_URL: str = "https://api.siliconflow.cn/v1"
    RERANK_API_KEY: str = ""

    # JEV 意图路由（TypeSafe System One，非 OpenAI 兼容协议）
    # 未配置 JEV_API_KEY 时自动停用并走规则 + 轻量模型降级，保证测试/CI 不联网
    JEV_ENABLED: bool = True
    JEV_API_KEY: str = ""
    # 兼容 EdgeOne Makers 平台的 Key 命名
    MAKERS_MODELS_KEY: str = ""
    JEV_ENDPOINT: str = "https://ai-gateway.edgeone.link/v1/systemone"
    JEV_MODEL: str = "@makers/jev"
    JEV_CONCURRENCY: int = 24
    JEV_TIMEOUT_S: float = 10.0
    # 路由低置信度阈值：JEV 低于该值先降级；降级仍低于该值才触发人工确认
    JEV_LOW_CONFIDENCE_THRESHOLD: float = 0.60
    # 待确认路由选择的有效期（分钟）
    ROUTE_CONFIRM_TTL_MINUTES: int = 30

    # JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    # 文件存储
    UPLOAD_DIR: str = "./data/uploads"
    MAX_FILE_SIZE_MB: int = 5

    # Chroma 向量库
    CHROMA_DIR: str = "./chroma"
    # 独立 Chroma 服务模式（多 worker 部署必配）：留空则使用上面的进程内本地模式
    CHROMA_HTTP_HOST: str = ""
    CHROMA_HTTP_PORT: int = 8000

    # 应用
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # 知识库检索权重
    BM25_WEIGHT: float = 0.4
    VECTOR_WEIGHT: float = 0.6
    RAG_TOP_K: int = 5

    # 检索重排序：默认关闭（生产采纳需评测裁决，见检索调参记录）
    RAG_RERANK_ENABLED: bool = False
    RAG_RERANK_CANDIDATES: int = 20

    # 比价权重默认值
    COMPARE_WEIGHT_PRICE: float = 0.4
    COMPARE_WEIGHT_HISTORY: float = 0.3
    COMPARE_WEIGHT_DELIVERY: float = 0.2
    COMPARE_WEIGHT_PAYMENT: float = 0.1

    # 对话记忆
    MEMORY_RECENT_TURNS: int = 6
    MEMORY_COMPRESS_THRESHOLD: float = 0.7

    # LLM 并发闸门：各档位进程内最大在途请求数与单次调用超时秒数
    # （0 表示该档位不限制并发；超时仅作用于非流式调用，流式只排队不设总超时）
    # 注意：多 worker 部署时实际在途上限 = 配置值 × worker 数（信号量为进程内资源）
    LLM_LIGHT_CONCURRENCY: int = 24
    LLM_MEDIUM_CONCURRENCY: int = 16
    LLM_HEAVY_CONCURRENCY: int = 8
    EMBEDDING_CONCURRENCY: int = 16
    RERANK_CONCURRENCY: int = 8
    LLM_LIGHT_TIMEOUT_S: float = 60.0
    LLM_MEDIUM_TIMEOUT_S: float = 180.0
    LLM_HEAVY_TIMEOUT_S: float = 300.0
    EMBEDDING_TIMEOUT_S: float = 60.0
    RERANK_TIMEOUT_S: float = 30.0
    # 非流式调用的总尝试次数（仅针对网络类瞬时错误重试）与退避起始秒数
    LLM_RETRY_ATTEMPTS: int = 2
    LLM_RETRY_BACKOFF_S: float = 1.0

    @property
    def jev_api_key(self) -> str:
        """JEV Key：优先 JEV_API_KEY，兼容 MAKERS_MODELS_KEY。"""
        return self.JEV_API_KEY or self.MAKERS_MODELS_KEY


settings = Settings()
