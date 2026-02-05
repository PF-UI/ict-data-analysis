"""
用户数据模式
"""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional


class UserBase(BaseModel):
    """用户基础模式"""
    name: str = Field(..., min_length=2, max_length=100, description="用户名")
    email: EmailStr = Field(..., description="邮箱")


class UserCreate(UserBase):
    """创建用户模式"""
    password: str = Field(..., min_length=6, max_length=72, description="密码（6-72个字符）")
    
    @field_validator('password')
    @classmethod
    def validate_password_length(cls, v: str) -> str:
        """验证密码长度（bcrypt 限制 72 字节）"""
        password_bytes = v.encode('utf-8')
        if len(password_bytes) > 72:
            raise ValueError('密码长度不能超过 72 字节（约 24 个中文字符或 72 个英文字符）')
        return v


class UserUpdate(BaseModel):
    """更新用户模式"""
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None


class User(UserBase):
    """用户响应模式"""
    id: int

    class Config:
        from_attributes = True


class UserInDB(User):
    """数据库中的用户模型（包含密码）"""
    hashed_password: str

