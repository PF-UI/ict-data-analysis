"""
安全相关工具函数
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import HTTPException, status
from app.core.config import settings

# JWT配置
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码
    
    直接使用 bcrypt 库，避免 passlib 兼容性问题
    """
    if not plain_password or not hashed_password:
        return False
    
    try:
        password_bytes = plain_password.encode('utf-8')
        # bcrypt 限制：密码不能超过 72 字节
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
        
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception as e:
        print(f"⚠️ 密码验证失败: {e}")
        return False


def get_password_hash(password: str) -> str:
    """
    生成密码哈希
    
    直接使用 bcrypt 库，避免 passlib 兼容性问题
    bcrypt 限制密码长度不能超过 72 字节
    """
    if not password:
        raise ValueError("密码不能为空")
    
    # bcrypt 限制：密码不能超过 72 字节
    # 将字符串编码为字节，如果超过 72 字节则截断
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        # 截断到 72 字节
        password_bytes = password_bytes[:72]
    
    # 直接使用 bcrypt 生成哈希
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建JWT访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """解码JWT令牌"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        print(f"❌ JWT 解码错误: {e}")
        return None
    except Exception as e:
        print(f"❌ Token 解码异常: {e}")
        return None

