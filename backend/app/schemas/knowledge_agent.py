"""知识库 Agent Pydantic Schema"""
from pydantic import BaseModel
from app.schemas.knowledge import SearchResult


class KnowledgeQueryInput(BaseModel):
    question: str
    session_id: str = ""


class KnowledgeQueryResult(BaseModel):
    answer: str
    sources: list[str] = []
    results: list[SearchResult] = []
    trend_chart_option: dict | None = None


class KnowledgeRecordExtract(BaseModel):
    needs_clarification: bool
    clarification_text: str | None = None
    extracted: dict | None = None


class KnowledgeSaveInput(BaseModel):
    record_type: str               # "purchase" / "quote"
    data: dict


class KnowledgeSaveResult(BaseModel):
    success: bool
    message: str
