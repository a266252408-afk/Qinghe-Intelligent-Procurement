"""知识库管理服务（三层：行业认知 / 长期历史 / 短期历史）
依据：docs/module-sdd/knowledge_base_manager.md
"""
import asyncio
import hashlib
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import KnowledgeDocError, SessionNotFoundError
from app.models.knowledge import ConversationSession, IndustryKnowledge, Message
from app.schemas.knowledge import (
    HistorySearchResult,
    MessageOut,
    PurchaseRecordCreate,
    QuoteRecordCreate,
    SearchResult,
    SessionCreate,
    SessionOut,
)

logger = logging.getLogger(__name__)

# Chroma 集合名称常量
_COL_INDUSTRY = "industry_knowledge"
_COL_HISTORY  = "purchase_history"

# BM25 语料缓存：team_id → (语料签名(文档数, 最大ID), 已建索引)
# 进程内缓存；多 worker 各自维护，签名不匹配（上传/删除文档）时自动重建
_BM25_CACHE: dict[int, tuple[tuple[int, int], Any]] = {}

logger = logging.getLogger(__name__)


def _jieba_tokenize(text: str) -> list[str]:
    """jieba 中文分词，用于 BM25（懒加载 jieba 避免启动时慢；须在线程池中调用）"""
    import jieba  # noqa: PLC0415
    return list(jieba.cut(text))


def _compact_match_text(text: str) -> str:
    """统一 PDF 兼容字符并移除空白，供查询短语精确匹配。"""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"\s+", "", normalized)


def _source_file_name(source_file: str | None) -> str | None:
    """仅保留来源文件名，避免把服务器存储路径暴露给前端。"""
    if not source_file:
        return None
    name = re.split(r"[\\/]", source_file)[-1]
    if re.fullmatch(r"[0-9a-f]{32}\.[a-z0-9]+", name, flags=re.IGNORECASE):
        return "历史上传文档（原始文件名未记录）"
    return name or None


def _parse_date(value: str | None):
    """将向量元数据日期转换为 date，异常值按空处理。"""
    from datetime import date

    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _get_chroma(collection: str):
    """懒加载 Chroma 实例。

    配置了 CHROMA_HTTP_HOST 时连接独立 Chroma 服务（多 worker 部署必用，
    嵌入式多进程写不安全）；否则回退进程内本地模式（开发环境默认）。
    """
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "FALSE")
    from langchain_chroma import Chroma
    from app.services.llm_factory import LLMFactory
    if settings.CHROMA_HTTP_HOST:
        import chromadb
        client = chromadb.HttpClient(
            host=settings.CHROMA_HTTP_HOST,
            port=settings.CHROMA_HTTP_PORT,
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        return Chroma(
            collection_name=collection,
            embedding_function=LLMFactory.get_embedding(),
            client=client,
        )
    return Chroma(
        collection_name=collection,
        embedding_function=LLMFactory.get_embedding(),
        persist_directory=settings.CHROMA_DIR,
    )


def clean_knowledge_text(content: str) -> str:
    """清洗知识文档文本，去除控制字符、空行噪声和常见扫描分隔线。"""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", normalized)
    lines: list[str] = []
    for raw_line in normalized.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line or re.fullmatch(r"[-_=*~·. ]{3,}", line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def split_knowledge_text(content: str) -> list[str]:
    """使用递归分块器切分清洗后的文本，保留适量上下文重叠。"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=512,
        chunk_overlap=100,
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
    )
    return splitter.split_text(content)


async def _rerank_candidates(query: str, results: list[Any],
                             db: AsyncSession, timing: dict | None) -> list[Any]:
    """二阶段语义重排序：rerank 客户端对候选打分重排。

    失败或未配置时返回原顺序（降级保命）；成功时未被 API 返回的候选
    （如 top_n 截断）按原相对顺序追加在后。
    """
    import time as _time

    from app.services.llm_factory import LLMFactory

    _t = _time.perf_counter()
    try:
        client = LLMFactory.get_rerank_client()
        ranked = await client.rerank(
            query, [r.page_content for r in results], session=db,
        )
    except Exception as exc:  # noqa: BLE001 — rerank 客户端异常不影响主链路
        logger.warning("行业知识 rerank 环节异常，退回混排原序：%s", exc)
        ranked = []
    if timing is not None:
        timing["rerank_ms"] = round((_time.perf_counter() - _t) * 1000, 1)
    if not ranked:
        return results
    seen = {idx for idx, _ in ranked}
    ordered = [results[idx] for idx, _ in ranked if 0 <= idx < len(results)]
    ordered += [r for i, r in enumerate(results) if i not in seen]
    # 内容去重（与精确匹配前置环节同款口径）
    unique: list[Any] = []
    content_keys: set[str] = set()
    for document in ordered:
        key = _compact_match_text(document.page_content)
        if key not in content_keys:
            content_keys.add(key)
            unique.append(document)
    return unique


def _prioritize_exact_matches(
    query: str,
    docs_db: list[IndustryKnowledge],
    retrieved: list[Any],
) -> list[Any]:
    """将查询短语直接出现的分块置于向量/关键词混排结果之前。"""
    from langchain_core.documents import Document

    query_key = _compact_match_text(query)
    exact_records = sorted(
        (
            record
            for record in docs_db
            if len(query_key) >= 2 and query_key in _compact_match_text(record.content)
        ),
        key=lambda record: _compact_match_text(record.content).find(query_key),
    )
    exact_docs = [
        Document(
            page_content=record.content,
            metadata={"source_file": record.source_file, "team_id": record.team_id},
        )
        for record in exact_records
    ]
    ordered = exact_docs + retrieved
    seen: set[str] = set()
    unique: list[Any] = []
    for document in ordered:
        content_key = _compact_match_text(document.page_content)
        if content_key not in seen:
            seen.add(content_key)
            unique.append(document)
    return unique


def _apply_exact_soft_boost(query: str, retrieved: list[Any], boost: float) -> list[Any]:
    """精确命中软加分：命中块按基础排名分加 boost 后重排，不无条件置顶。

    基础分沿用混合检索的位次分（1.0 - i*0.1），加分后重排保持稳定性
    （同分按原位次），避免排序抖动。
    """
    query_key = _compact_match_text(query)
    if len(query_key) < 2 or not retrieved:
        return retrieved
    scored = []
    for index, document in enumerate(retrieved):
        base = 1.0 - index * 0.1
        bonus = boost if query_key in _compact_match_text(document.page_content) else 0.0
        scored.append((base + bonus, index, document))
    scored.sort(key=lambda item: (-item[0], item[1]))
    seen: set[str] = set()
    unique: list[Any] = []
    for _, _, document in scored:
        content_key = _compact_match_text(document.page_content)
        if content_key in seen:
            continue
        seen.add(content_key)
        unique.append(document)
    return unique


class KnowledgeBaseManager:
    """三层知识库统一管理接口"""

    # ── 行业认知库 ─────────────────────────────────────────────────────────

    @staticmethod
    async def upload_industry_doc(
        team_id: int,
        source_file: str,
        content: str,
        db: AsyncSession,
    ) -> list[IndustryKnowledge]:
        """清洗并递归切分文档，向量化写入 Chroma，同时保存分块索引。"""
        from langchain_core.documents import Document
        cleaned = clean_knowledge_text(content)
        chunks = split_knowledge_text(cleaned)
        if not chunks:
            raise KnowledgeDocError("知识库文档没有可用文本")

        vector_ids = [
            hashlib.md5(f"{team_id}:{source_file}:{index}:{chunk}".encode()).hexdigest()
            for index, chunk in enumerate(chunks)
        ]
        try:
            chroma = _get_chroma(_COL_INDUSTRY)
            # Chroma add_documents 是同步调用（内嵌同步 embedding 请求），
            # 放入线程池避免长时间阻塞事件循环
            await asyncio.to_thread(
                chroma.add_documents,
                documents=[
                    Document(
                        page_content=chunk,
                        metadata={
                            "team_id": team_id,
                            "source": source_file,
                            "chunk_index": index,
                        },
                    )
                    for index, chunk in enumerate(chunks)
                ],
                ids=vector_ids,
            )
        except Exception as exc:
            logger.error("Chroma 写入失败：%s", exc)
            raise KnowledgeDocError(f"文档向量化失败：{exc}") from exc

        records = [
            IndustryKnowledge(
                team_id=team_id,
                source_file=source_file,
                content=chunk,
                vector_id=vector_id,
            )
            for chunk, vector_id in zip(chunks, vector_ids)
        ]
        db.add_all(records)
        await db.flush()
        return records

    @staticmethod
    async def list_industry_docs(team_id: int, db: AsyncSession) -> list[dict]:
        """按来源文件汇总当前团队已上传的行业文档及知识分块数。"""
        stmt = (
            select(IndustryKnowledge.source_file, func.count().label("chunks"))
            .where(IndustryKnowledge.team_id == team_id)
            .group_by(IndustryKnowledge.source_file)
            .order_by(func.min(IndustryKnowledge.id))
        )
        rows = (await db.execute(stmt)).all()
        return [{"source_file": source_file, "chunks": chunks} for source_file, chunks in rows]

    @staticmethod
    async def search_industry(
        query: str,
        team_id: int,
        db: AsyncSession,
        top_k: int = 5,
        *,
        # 精确匹配默认关闭（调参记录1.2裁决：rerank 开启后 prepend 仅 +0.3pp MRR）；
        # 保留参数供 rerank 不可用时兜底与评测 A/B，一行可回滚
        exact_strategy: str = "off",
        exact_boost: float = 0.2,
        # 评测数据裁决（检索调参记录）：0.5/0.5 较 0.4/0.6
        # 在 test 集 Recall@5 0.77→1.00，validation 持平；园林文档规格词多，BM25 应占半壁
        bm25_weight: float = 0.5,
        vector_weight: float = 0.5,
        rerank_enabled: bool | None = None,
        rerank_candidates: int | None = None,
        timing: dict | None = None,
    ) -> list[SearchResult]:
        """混合检索（向量 + BM25）行业知识库，返回 Top-K。

        可选参数（评测调参用，默认值即生产行为）：
        - exact_strategy: 精确匹配环节策略，prepend=命中前置(可选兜底，默认关闭) /
          soft_boost=命中加分不置顶 / off=关闭(默认)
        - exact_boost: soft_boost 策略下的加分值
        - bm25_weight / vector_weight: 混合检索权重
        - rerank_enabled: 二阶段语义重排序开关；None 读 settings.RAG_RERANK_ENABLED
        - rerank_candidates: 重排序候选池大小；None 读 settings.RAG_RERANK_CANDIDATES
        - timing: 传入 dict 时回填分环节耗时（毫秒），供评测计时
        """
        if exact_strategy not in {"prepend", "soft_boost", "off"}:
            raise ValueError(f"未知 exact_strategy：{exact_strategy}")
        use_rerank = settings.RAG_RERANK_ENABLED if rerank_enabled is None else rerank_enabled
        pool = rerank_candidates or settings.RAG_RERANK_CANDIDATES
        if use_rerank and pool < top_k:
            pool = top_k  # 候选池不得小于返回条数
        retrieval_k = pool if use_rerank else top_k
        import time as _time
        _t0 = _time.perf_counter()
        try:
            from langchain_core.documents import Document
            from langchain.retrievers import EnsembleRetriever
            from langchain_community.retrievers import BM25Retriever
        except ImportError:
            logger.warning("langchain 未安装，知识库检索不可用")
            return []

        stmt = (
            select(IndustryKnowledge)
            .where(IndustryKnowledge.team_id == team_id)
            .order_by(IndustryKnowledge.id)
        )
        docs_db = (await db.execute(stmt)).scalars().all()

        if not docs_db:
            return []

        lc_docs = [
            Document(
                page_content=d.content,
                metadata={
                    "source": d.source_file,
                    "source_file": d.source_file,
                    "team_id": team_id,
                },
            )
            for d in docs_db
        ]

        # BM25 语料构建包含全量文档 jieba 分词，是 CPU 密集操作：
        # 放线程池执行，并按"文档数+最大ID"签名缓存索引，语料未变时直接复用
        corpus_sig = (len(docs_db), docs_db[-1].id)
        cached = _BM25_CACHE.get(team_id)
        if cached is not None and cached[0] == corpus_sig:
            bm25 = cached[1]
        else:
            _t_build = _time.perf_counter()
            bm25 = await asyncio.to_thread(
                BM25Retriever.from_documents, lc_docs, preprocess_func=_jieba_tokenize
            )
            _BM25_CACHE[team_id] = (corpus_sig, bm25)
            if timing is not None:
                timing["bm25_build_ms"] = round((_time.perf_counter() - _t_build) * 1000, 1)
        bm25.k = retrieval_k

        from app.services.llm_gate import LLMGate
        try:
            chroma = _get_chroma(_COL_INDUSTRY)
            vector_retriever = chroma.as_retriever(
                search_kwargs={"k": retrieval_k, "filter": {"team_id": team_id}}
            )
            ensemble = EnsembleRetriever(
                retrievers=[bm25, vector_retriever],
                weights=[bm25_weight, vector_weight],
            )
            async with LLMGate.acquire("embedding"):
                _t_hybrid = _time.perf_counter()
                results = await ensemble.ainvoke(unicodedata.normalize("NFKC", query))
                if timing is not None:
                    timing["hybrid_ms"] = round((_time.perf_counter() - _t_hybrid) * 1000, 1)
        except Exception as exc:
            logger.warning("行业知识向量检索失败，降级为 BM25：%s", exc)
            async with LLMGate.acquire("embedding"):
                _t_hybrid = _time.perf_counter()
                results = await bm25.ainvoke(unicodedata.normalize("NFKC", query))
                if timing is not None:
                    timing["hybrid_ms"] = round((_time.perf_counter() - _t_hybrid) * 1000, 1)
        if use_rerank and results:
            results = await _rerank_candidates(query, results, db, timing)
        _t_exact = _time.perf_counter()
        if exact_strategy == "prepend":
            results = _prioritize_exact_matches(query, docs_db, results)
        elif exact_strategy == "soft_boost":
            results = _apply_exact_soft_boost(query, results, exact_boost)
        if timing is not None:
            timing["exact_ms"] = round((_time.perf_counter() - _t_exact) * 1000, 1)
            timing["total_ms"] = round((_time.perf_counter() - _t0) * 1000, 1)
        return [
            SearchResult(
                source="industry",
                source_file=_source_file_name(
                    r.metadata.get("source_file") or r.metadata.get("source")
                ),
                content=r.page_content,
                score=1.0 - i * 0.1,
            )
            for i, r in enumerate(results[:top_k])
        ]

    # ── 历史价格库 ─────────────────────────────────────────────────────────

    @staticmethod
    async def save_purchase_record(data: PurchaseRecordCreate) -> str:
        """将采购记录向量化写入历史价格库（Chroma）"""
        from langchain_core.documents import Document
        text = (
            f"品种:{data.species} 规格:{data.spec} 数量:{data.quantity}{data.unit} "
            f"项目:{data.project_name} 日期:{data.purchase_date}"
        )
        doc_id = hashlib.md5(f"purchase:{data.team_id}:{data.order_id}:{data.species}".encode()).hexdigest()
        try:
            chroma = _get_chroma(_COL_HISTORY)
            # 同步 embedding + 向量写入，放线程池避免阻塞事件循环
            await asyncio.to_thread(
                chroma.add_documents,
                documents=[Document(
                    page_content=text,
                    metadata={
                        "team_id": data.team_id,
                        "record_type": "purchase",
                        "species": data.species,
                        "spec": data.spec,
                        "order_id": data.order_id,
                    },
                )],
                ids=[doc_id],
            )
        except Exception as exc:
            logger.error("历史采购记录写入 Chroma 失败：%s", exc)
            raise KnowledgeDocError(f"记录写入失败：{exc}") from exc
        return doc_id

    @staticmethod
    async def save_quote_record(data: QuoteRecordCreate) -> str:
        """将报价记录向量化写入历史价格库（Chroma）"""
        from langchain_core.documents import Document
        text = (
            f"供应商:{data.supplier_name} 品种:{data.species} 规格:{data.spec} "
            f"单价:{data.unit_price} 日期:{data.quote_date}"
        )
        doc_id = hashlib.md5(
            f"quote:{data.team_id}:{data.order_id}:{data.supplier_name}:{data.species}".encode()
        ).hexdigest()
        try:
            chroma = _get_chroma(_COL_HISTORY)
            # 同步 embedding + 向量写入，放线程池避免阻塞事件循环
            await asyncio.to_thread(
                chroma.add_documents,
                documents=[Document(
                    page_content=text,
                    metadata={
                        "team_id": data.team_id,
                        "record_type": "quote",
                        "species": data.species,
                        "spec": data.spec,
                        "supplier_name": data.supplier_name,
                        "unit_price": data.unit_price,
                        "order_id": data.order_id,
                    },
                )],
                ids=[doc_id],
            )
        except Exception as exc:
            logger.error("报价记录写入 Chroma 失败：%s", exc)
            raise KnowledgeDocError(f"记录写入失败：{exc}") from exc
        return doc_id

    @staticmethod
    async def index_material_record(record) -> str:
        """将结构化长期材料记录写入历史向量集合。"""
        from langchain_core.documents import Document

        text = (
            f"供应商:{record.supplier_name} 材料:{record.material_name} 规格:{record.spec} "
            f"报价:{record.quote_price} 总价:{record.total_price} 成交价:{record.final_price} 日期:{record.quote_date}"
        )
        doc_id = f"material-history-{record.team_id}-{record.fingerprint}"
        chroma = _get_chroma(_COL_HISTORY)
        # 同步 embedding + 向量写入，放线程池避免阻塞事件循环
        await asyncio.to_thread(
            chroma.add_documents,
            documents=[Document(
                page_content=text,
                metadata={
                    "team_id": record.team_id,
                    "record_type": "material_history",
                    "species": record.material_name,
                    "spec": record.spec,
                    "supplier_name": record.supplier_name,
                    "unit_price": float(record.quote_price) if record.quote_price is not None else None,
                    "final_price": float(record.final_price) if record.final_price is not None else None,
                    "quote_date": str(record.quote_date),
                },
            )],
            ids=[doc_id],
        )
        return doc_id

    @staticmethod
    async def search_history(
        query: str,
        team_id: int,
        top_k: int = 5,
    ) -> list[HistorySearchResult]:
        """在历史价格库中混合检索（向量检索，BM25 依赖内存语料暂不可用时降级纯向量）"""
        try:
            chroma = _get_chroma(_COL_HISTORY)
            # 同步向量查询（内嵌同步 embedding 请求），放线程池避免阻塞事件循环
            raw = await asyncio.to_thread(
                chroma.similarity_search_with_score,
                query,
                k=top_k,
                filter={"team_id": team_id},
            )
        except Exception as exc:
            logger.warning("历史价格检索失败：%s", exc)
            return []

        results: list[HistorySearchResult] = []
        for doc, score in raw:
            meta = doc.metadata
            results.append(HistorySearchResult(
                record_type=meta.get("record_type", "unknown"),
                species=meta.get("species", ""),
                spec=meta.get("spec", ""),
                price=meta.get("unit_price"),
                supplier=meta.get("supplier_name"),
                date=_parse_date(meta.get("quote_date")),
                score=float(1 - score),  # Chroma 返回距离，转为相似度
            ))
        return results
    # ── 对话会话 ───────────────────────────────────────────────────────────

    @staticmethod
    async def create_session(
        user_id: int,
        data: SessionCreate,
        db: AsyncSession,
    ) -> SessionOut:
        """创建新对话会话"""
        session = ConversationSession(
            user_id=user_id,
            project_id=data.project_id,
            title=data.title,
        )
        db.add(session)
        await db.flush()
        return SessionOut(
            session_id=session.id,
            user_id=session.user_id,
            project_id=session.project_id,
            title=session.title,
            created_at=session.created_at,
        )

    @staticmethod
    async def get_session_messages(
        session_id: int,
        user_id: int,
        db: AsyncSession,
    ) -> list[MessageOut]:
        """获取会话消息列表（仅本人）"""
        stmt = (
            select(ConversationSession)
            .options(selectinload(ConversationSession.messages))
            .where(ConversationSession.id == session_id, ConversationSession.user_id == user_id)
        )
        session = (await db.execute(stmt)).scalar_one_or_none()
        if session is None:
            raise SessionNotFoundError()
        return [
            MessageOut(
                message_id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                metadata=m.metadata_json,
                created_at=m.created_at,
            )
            for m in session.messages
        ]

    @staticmethod
    async def list_sessions(
        user_id: int, project_id: int, db: AsyncSession
    ) -> list[SessionOut]:
        """按项目返回当前用户的会话列表，最新会话在前。"""
        stmt = select(ConversationSession).where(
            ConversationSession.user_id == user_id,
            ConversationSession.project_id == project_id,
        ).order_by(ConversationSession.created_at.desc())
        rows = (await db.execute(stmt)).scalars().all()
        return [SessionOut(
            session_id=row.id,
            user_id=row.user_id,
            project_id=row.project_id,
            title=row.title,
            created_at=row.created_at,
        ) for row in rows]

    @staticmethod
    async def delete_session(session_id: int, user_id: int, db: AsyncSession) -> None:
        """删除当前用户的会话及其消息。"""
        from sqlalchemy import delete
        result = await db.execute(delete(ConversationSession).where(
            ConversationSession.id == session_id,
            ConversationSession.user_id == user_id,
        ))
        if result.rowcount == 0:
            raise SessionNotFoundError()
        await db.flush()

    @staticmethod
    async def ensure_session_owned(session_id: int, user_id: int, db: AsyncSession) -> None:
        """校验会话归属，不存在或不属于该用户时抛 SessionNotFoundError。

        独立于 add_message：调用方（ChatAgent）需要在"校验→提交释放读快照→纯写事务"
        之间控制提交时机（SQLite WAL 读快照升级写锁的 busy 规避）。
        """
        stmt = select(ConversationSession.id).where(
            ConversationSession.id == session_id,
            ConversationSession.user_id == user_id,
        )
        if (await db.execute(stmt)).scalar_one_or_none() is None:
            raise SessionNotFoundError()

    @staticmethod
    async def add_message(
        session_id: int,
        user_id: int,
        role: str,
        content: str,
        db: AsyncSession,
        metadata: dict | None = None,
    ) -> MessageOut:
        """向会话追加一条消息（user / assistant）"""
        stmt = select(ConversationSession).where(
            ConversationSession.id == session_id,
            ConversationSession.user_id == user_id,
        )
        session = (await db.execute(stmt)).scalar_one_or_none()
        if session is None:
            raise SessionNotFoundError()

        msg = Message(
            session_id=session_id,
            role=role,
            content=content,
            metadata_json=metadata,
        )
        db.add(msg)
        await db.flush()
        return MessageOut(
            message_id=msg.id,
            session_id=msg.session_id,
            role=msg.role,
            content=msg.content,
            metadata=msg.metadata_json,
            created_at=msg.created_at,
        )
