"""
认证相关数据模式
"""
from pydantic import BaseModel, EmailStr
from typing import Optional


class Token(BaseModel):
    """Token响应模式"""
    access_token: str
    token_type: str


class TokenData(BaseModel):
    """Token数据模式"""
    email: Optional[str] = None


class LoginRequest(BaseModel):
    """登录请求模式"""
    email: EmailStr
    password: str
