"""对话历史 API模型。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatSessionOut(BaseModel):
    id: int = Field(description="行主键")
    session_id: str = Field(description="前端使用的 session_id")
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content_type: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionTitleUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
