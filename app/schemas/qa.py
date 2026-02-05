"""
问答系统相关的数据模式
"""
from pydantic import BaseModel, Field


class QuestionRequest(BaseModel):
    """问题请求"""
    question: str = Field(..., description="用户提出的问题", min_length=1)


class QuestionResponse(BaseModel):
    """问题响应"""
    answer: str = Field(..., description="AI回答")
    question: str = Field(..., description="用户提出的问题")
