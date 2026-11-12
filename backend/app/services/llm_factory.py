"""LLM 工厂模块 — 按档位创建并缓存 LangChain 实例
依据：docs/module-sdd/llm_factory.md
"""
import logging
from typing import TYPE_CHECKING, ClassVar

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.core.config import settings
from app.core.exceptions import ConfigError

if TYPE_CHECKING:
    from app.services.jev_client import JevClient

logger = logging.getLogger(__name__)


def _require(value: str, name: str) -> str:
    """检查必填配置项，空值抛 ConfigError"""
    if not value:
        raise ConfigError(f"环境变量 {name} 未配置")
    return value


class LLMFactory:
    """按档位创建 LangChain LLM 实例，进程内单例缓存"""

    _instances: ClassVar[dict[str, object]] = {}

    @classmethod
    def get_light(cls) -> BaseChatModel:
        """轻量档：结构化提取、路由分类、摘要压缩"""
        if "light" not in cls._instances:
            cls._instances["light"] = ChatOpenAI(
                model=_require(settings.LLM_LIGHT_MODEL, "LLM_LIGHT_MODEL"),
                base_url=_require(settings.LLM_LIGHT_BASE_URL, "LLM_LIGHT_BASE_URL"),
                api_key=_require(settings.LLM_LIGHT_API_KEY, "LLM_LIGHT_API_KEY"),
            )
        return cls._instances["light"]  # type: ignore[return-value]

    @classmethod
    def get_medium(cls) -> BaseChatModel:
        """中量档：对话、检索回答、趋势分析"""
        if "medium" not in cls._instances:
            cls._instances["medium"] = ChatOpenAI(
                model=_require(settings.LLM_MEDIUM_MODEL, "LLM_MEDIUM_MODEL"),
                base_url=_require(settings.LLM_MEDIUM_BASE_URL, "LLM_MEDIUM_BASE_URL"),
                api_key=_require(settings.LLM_MEDIUM_API_KEY, "LLM_MEDIUM_API_KEY"),
            )
        return cls._instances["medium"]  # type: ignore[return-value]

    @classmethod
    def get_heavy(cls) -> BaseChatModel:
        """重量档：比价建议、复杂推理"""
        if "heavy" not in cls._instances:
            cls._instances["heavy"] = ChatOpenAI(
                model=_require(settings.LLM_HEAVY_MODEL, "LLM_HEAVY_MODEL"),
                base_url=_require(settings.LLM_HEAVY_BASE_URL, "LLM_HEAVY_BASE_URL"),
                api_key=_require(settings.LLM_HEAVY_API_KEY, "LLM_HEAVY_API_KEY"),
            )
        return cls._instances["heavy"]  # type: ignore[return-value]

    @classmethod
    def get_embedding(cls) -> Embeddings:
        """嵌入模型：向量化，供 Chroma 使用"""
        if "embedding" not in cls._instances:
            cls._instances["embedding"] = OpenAIEmbeddings(
                model=_require(settings.EMBEDDING_MODEL, "EMBEDDING_MODEL"),
                base_url=_require(settings.EMBEDDING_BASE_URL, "EMBEDDING_BASE_URL"),
                api_key=_require(settings.EMBEDDING_API_KEY, "EMBEDDING_API_KEY"),
            )
        return cls._instances["embedding"]  # type: ignore[return-value]

    @classmethod
    def get_rerank_client(cls):
        """重排序客户端：RAG 二阶段精排（Cohere 风格 /rerank 接口）"""
        from app.services.rerank_client import RerankClient

        if "rerank" not in cls._instances:
            cls._instances["rerank"] = RerankClient(
                model=_require(settings.RERANK_MODEL, "RERANK_MODEL"),
                base_url=_require(settings.RERANK_BASE_URL, "RERANK_BASE_URL"),
                api_key=settings.RERANK_API_KEY,  # 未配 key 时客户端空跑返回空（降级）
                timeout_s=settings.RERANK_TIMEOUT_S,
            )
        return cls._instances["rerank"]

    @classmethod
    def get_jev(cls) -> "JevClient":
        """JEV 意图路由客户端（TypeSafe System One 协议，非 OpenAI 兼容）"""
        from app.services.jev_client import JevClient

        if "jev" not in cls._instances:
            cls._instances["jev"] = JevClient(
                api_key=_require(settings.jev_api_key, "JEV_API_KEY 或 MAKERS_MODELS_KEY"),
                endpoint=settings.JEV_ENDPOINT,
                model=settings.JEV_MODEL,
                timeout_s=settings.JEV_TIMEOUT_S,
            )
        return cls._instances["jev"]  # type: ignore[return-value]

    @classmethod
    def reset(cls) -> None:
        """清空实例缓存（测试隔离用）"""
        cls._instances.clear()
