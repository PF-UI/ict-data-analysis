"""
依赖注入函数
"""
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status, WebSocket
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
from app.core.security import decode_access_token
from app.database import get_db, SessionLocal
from app.models.user import User as UserModel

# OAuth2密码流程
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> UserModel:
    """
    获取当前用户（依赖注入函数）
    用于需要认证的路由
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # 调试：打印接收到的 token（仅前20个字符）
    print(f"🔑 接收到的 token: {token[:20]}..." if len(token) > 20 else f"🔑 接收到的 token: {token}")
    
    payload = decode_access_token(token)
    if payload is None:
        print("❌ Token 解码失败")
        raise credentials_exception
    
    print(f"✅ Token 解码成功，payload: {payload}")
    
    # JWT sub 字段是字符串，需要转换为整数
    user_id_str = payload.get("sub")
    if user_id_str is None:
        print(f"❌ Payload 中缺少 'sub' 字段，payload: {payload}")
        raise credentials_exception
    
    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        print(f"❌ 无法将 'sub' 转换为整数: {user_id_str}")
        raise credentials_exception
    
    print(f"🔍 查找用户 ID: {user_id}")
    
    # 从数据库获取用户信息
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        print(f"❌ 用户 ID {user_id} 不存在")
        raise credentials_exception
    
    print(f"✅ 找到用户: {user.email}")
    return user


async def get_current_user_ws(
    websocket: WebSocket,
    token: Optional[str] = None
) -> Optional[UserModel]:
    """
    获取当前用户（WebSocket 认证）
    从 query 参数或 headers 中获取 token
    """
    # 尝试从 query 参数获取 token
    if not token:
        token = websocket.query_params.get("token")
    
    # 尝试从 headers 获取 token
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    if not token:
        await websocket.close(code=1008, reason="缺少认证令牌")
        return None
    
    payload = decode_access_token(token)
    if payload is None:
        await websocket.close(code=1008, reason="无效的认证令牌")
        return None
    
    user_id_str = payload.get("sub")
    if user_id_str is None:
        await websocket.close(code=1008, reason="无效的令牌格式")
        return None
    
    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        await websocket.close(code=1008, reason="无效的用户ID")
        return None
    
    # 创建数据库会话
    db = SessionLocal()
    try:
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        if user is None:
            await websocket.close(code=1008, reason="用户不存在")
            return None
        return user
    finally:
        db.close()

