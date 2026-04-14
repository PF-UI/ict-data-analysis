"""对话历史：与 LangGraph 检查点无关的业务侧消息持久化。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.history_chat import ChatMessage, ChatSession

TITLE_MAX_LEN = 80


def title_from_first_line(question: str) -> str:
    line = (question or "").strip().split("\n", 1)[0].strip()
    if not line:
        return "新对话"
    if len(line) > TITLE_MAX_LEN:
        return line[: TITLE_MAX_LEN - 1] + "…"
    return line


def get_or_create_chat_session(
    db: Session,
    *,
    user_id: int,
    session_id: str,
    question: str,
) -> ChatSession:
    row = (
        db.query(ChatSession)
        .filter(
            ChatSession.user_id == user_id,
            ChatSession.session_id == session_id,
        )
        .first()
    )
    if row:
        return row
    row = ChatSession(
        user_id=user_id,
        session_id=session_id,
        title=title_from_first_line(question),
    )
    db.add(row)
    db.flush()
    return row


def touch_session(db: Session, session: ChatSession) -> None:
    session.updated_at = datetime.now()


def append_chat_message(
    db: Session,
    *,
    session: ChatSession,
    role: str,
    content: str,
    content_type: str = "text",
) -> ChatMessage:
    msg = ChatMessage(
        chat_session_id=session.id,
        role=role,
        content_type=content_type,
        content=content,
    )
    db.add(msg)
    touch_session(db, session)
    return msg


def list_user_sessions(
    db: Session,
    *,
    user_id: int,
    skip: int = 0,
    limit: int = 50,
) -> list[ChatSession]:
    return (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_session_for_user(
    db: Session,
    *,
    user_id: int,
    session_id: str,
) -> ChatSession | None:
    return (
        db.query(ChatSession)
        .filter(
            ChatSession.user_id == user_id,
            ChatSession.session_id == session_id,
        )
        .first()
    )


def list_session_messages(
    db: Session,
    *,
    user_id: int,
    session_id: str,
) -> list[ChatMessage] | None:
    sess = get_session_for_user(db, user_id=user_id, session_id=session_id)
    if sess is None:
        return None
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.chat_session_id == sess.id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )
