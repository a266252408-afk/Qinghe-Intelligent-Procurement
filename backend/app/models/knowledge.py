"""知识库相关 ORM 模型：行业认知库、会话、消息"""
from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class IndustryKnowledge(Base):
    """行业认知库文档索引（结构化部分，向量存 Chroma）"""
    __tablename__ = "industry_knowledge"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    source_file: Mapped[str] = mapped_column(String(500), nullable=False)  # 原始文件路径
    content: Mapped[str] = mapped_column(Text, nullable=False)             # 文档摘要或全文
    vector_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Chroma 文档 ID


class ConversationSession(Base):
    """对话会话"""
    __tablename__ = "conversation_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="新会话")

    messages: Mapped[list["Message"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    """会话消息"""
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)   # user / assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    session: Mapped["ConversationSession"] = relationship(back_populates="messages")
