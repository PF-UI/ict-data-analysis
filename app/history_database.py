"""
智能问答对话历史：PostgreSQL 同步引擎（与 LangGraph 检查点同库、独立表）。
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

HistoryBase = declarative_base()

_history_engine = None
HistorySessionLocal: sessionmaker | None = None


def _sync_sqlalchemy_url(agent_uri: str) -> str:
    """将 postgresql:// 转为 SQLAlchemy 同步驱动 postgresql+psycopg://。"""
    u = agent_uri.strip()
    if u.startswith("postgresql+psycopg://"):
        return u
    if u.startswith("postgresql://"):
        return "postgresql+psycopg://" + u[len("postgresql://") :]
    if u.startswith("postgres://"):
        return "postgresql+psycopg://" + u[len("postgres://") :]
    return u


def get_history_database_url() -> str:
    uri = (settings.get_agent_memory_database_url() or "").strip()
    if not uri:
        raise RuntimeError(
            "未配置 PostgreSQL 记忆库 URL，无法启用对话历史。"
            "请在 .env 中设置 AGENT_MEMORY_DATABASE_URL 或 DB_USER/DB_HOST/DB_NAME 等。"
        )
    return _sync_sqlalchemy_url(uri)


def _ensure_engine() -> None:
    global _history_engine, HistorySessionLocal
    if _history_engine is not None:
        return
    url = get_history_database_url()
    _history_engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=min(settings.DB_POOL_SIZE, 10),
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=settings.DB_POOL_RECYCLE,
        echo=False,
    )
    HistorySessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=_history_engine
    )


def init_history_db() -> None:
    """创建 chat_sessions / chat_messages（仅 PostgreSQL）。"""
    import importlib

    importlib.import_module("app.models.history_chat")  # 注册表到 HistoryBase.metadata

    _ensure_engine()
    assert _history_engine is not None
    try:
        with _history_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        HistoryBase.metadata.create_all(bind=_history_engine)
    except OperationalError as e:
        raise RuntimeError(
            "无法连接 PostgreSQL 对话历史库，请检查 AGENT_MEMORY_DATABASE_URL 或 DB_*。"
        ) from e


def get_history_db():
    _ensure_engine()
    assert HistorySessionLocal is not None
    db = HistorySessionLocal()
    try:
        yield db
    finally:
        db.close()


def new_history_session():
    """供 WebSocket 等非依赖注入场景创建会话（须已在 lifespan 中调用过 init_history_db）。"""
    _ensure_engine()
    assert HistorySessionLocal is not None
    return HistorySessionLocal()
