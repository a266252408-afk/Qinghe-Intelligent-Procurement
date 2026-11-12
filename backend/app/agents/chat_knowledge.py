"""对话中的行业知识问答分发 — 封装 KnowledgeAgent.query 与结果帧。"""
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.knowledge import KnowledgeAgent
from app.schemas.knowledge_agent import KnowledgeQueryInput

_COMMAND_PREFIXES = ("/知识", "/knowledge")
_EMPTY_HINT = "请在 /知识 后写明要查询的问题，例如：/知识 香樟树苗怎么养护。"


class KnowledgeAnswer(BaseModel):
    """知识问答结果：answer 进对话，frame 进结果抽屉。"""

    answer: str
    frame: dict


def strip_knowledge_command(message: str) -> str:
    """去掉 /知识 或 /knowledge 前缀，保留实际问题。"""
    text = message.strip()
    for prefix in _COMMAND_PREFIXES:
        if text.lower().startswith(prefix.lower()):
            return text[len(prefix):].strip()
    return text


async def answer_knowledge_question(
    question: str,
    session_id: str,
    team_id: int,
    db: AsyncSession,
) -> KnowledgeAnswer:
    """调用 KnowledgeAgent 检索行业知识库，并组装来源帧。"""
    text = strip_knowledge_command(question)
    if not text:
        return KnowledgeAnswer(
            answer=_EMPTY_HINT,
            frame={"sources": [], "results": []},
        )

    result = await KnowledgeAgent().query(
        KnowledgeQueryInput(question=text, session_id=session_id),
        team_id,
        db,
    )
    frame = {
        "sources": list(result.sources),
        "results": [item.model_dump(mode="json") for item in result.results],
    }
    return KnowledgeAnswer(answer=result.answer, frame=frame)
