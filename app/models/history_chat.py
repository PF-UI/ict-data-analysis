"""问答对话会话与消息：仅存 PostgreSQL（HistoryBase），user_id 无外键跨 MySQL。"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.history_database import HistoryBase


class ChatSession(HistoryBase):
    """一轮可续聊会话，与 WebSocket 传入的 session_id（UUID）一一对应。"""

    __tablename__ = "chat_sessions"
    __table_args__ = (
        UniqueConstraint("user_id", "session_id", name="uq_chat_sessions_user_session"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    user_id = Column(
        Integer,
        nullable=False,
        index=True,
        comment="用户 ID（与 MySQL users 逻辑关联，无外键）",
    )
    session_id = Column(
        String(64),
        nullable=False,
        comment="前端会话 ID，与 /qa/ask/ws 的 session_id 一致",
    )
    title = Column(String(255), nullable=False, comment="侧边栏标题（通常为首问摘要）")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        comment="最后活跃时间",
    )


class ChatMessage(HistoryBase):
    """一条用户或助手消息。"""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    chat_session_id = Column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属会话表主键",
    )
    role = Column(String(20), nullable=False, comment="user | assistant | system")
    content_type = Column(
        String(32),
        nullable=False,
        server_default="text",
        comment="text 等，预留卡片/富文本",
    )
    content = Column(Text, nullable=False, comment="正文")
    created_at = Column(
        DateTime,
        server_default=func.now(),
        index=True,
        comment="消息时间",
    )
