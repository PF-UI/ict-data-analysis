"""
认证相关路由
"""
from datetime import timedelta
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.schemas.auth import Token, LoginRequest
from app.schemas.user import User, UserCreate
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.config import settings
from app.database import get_db
from app.models.user import User as UserModel

router = APIRouter()


def get_user_by_email(db: Session, email: str):
    """根据邮箱获取用户"""
    return db.query(UserModel).filter(UserModel.email == email).first()


def authenticate_user(db: Session, email: str, password: str):
    """验证用户"""
    user = get_user_by_email(db, email)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    用户登录接口
    支持OAuth2密码流程
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email},  # JWT sub 必须是字符串
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login/json", response_model=Token)
async def login_json(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    用户登录接口（JSON格式）
    """
    user = authenticate_user(db, login_data.email, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email},  # JWT sub 必须是字符串
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/register", response_model=User, status_code=201)
async def register(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """
    用户注册接口（不需要认证）
    """
    try:
        # 检查邮箱是否已存在
        existing_user = get_user_by_email(db, user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱已被注册"
            )
        
        # 创建新用户
        hashed_password = get_password_hash(user_data.password)
        db_user = UserModel(
            email=user_data.email,
            name=user_data.name,
            hashed_password=hashed_password
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        # 返回用户信息（不包含密码）
        return User(
            id=db_user.id,
            email=db_user.email,
            name=db_user.name
        )
    except HTTPException:
        # 重新抛出 HTTP 异常
        raise
    except Exception as e:
        # 回滚事务
        db.rollback()
        # 记录详细错误信息
        import traceback
        error_detail = str(e)
        traceback_str = traceback.format_exc()
        print(f"❌ 用户注册失败: {error_detail}")
        print(f"📋 错误堆栈:\n{traceback_str}")
        
        # 返回友好的错误信息
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"注册失败: {error_detail}"
        )

