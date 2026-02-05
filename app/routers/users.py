"""
用户相关路由
"""
from sqlalchemy.orm import Session
from fastapi import APIRouter, HTTPException, Depends
from typing import List
from app.schemas.user import User, UserCreate, UserUpdate
from app.core.security import get_password_hash
from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User as UserModel

router = APIRouter()


@router.get("/me", response_model=User)
async def get_current_user_info(
    current_user: UserModel = Depends(get_current_user)
):
    """获取当前登录用户信息（需要认证）"""
    return User(id=current_user.id, email=current_user.email, name=current_user.name)


@router.get("/", response_model=List[User])
async def get_users(
    skip: int = 0,
    limit: int = 100,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户列表（需要认证）"""
    users = db.query(UserModel).offset(skip).limit(limit).all()
    return [User(id=u.id, email=u.email, name=u.name) for u in users]


@router.get("/{user_id}", response_model=User)
async def get_user(
    user_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """根据ID获取用户（需要认证）"""
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="用户未找到")
    return User(id=user.id, email=user.email, name=user.name)


@router.post("/", response_model=User, status_code=201)
async def create_user(
    user: UserCreate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建新用户（需要认证）"""
    # 检查邮箱是否已存在
    existing_user = db.query(UserModel).filter(UserModel.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="邮箱已存在")
    
    hashed_password = get_password_hash(user.password)
    db_user = UserModel(
        email=user.email,
        name=user.name,
        hashed_password=hashed_password
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return User(id=db_user.id, email=db_user.email, name=db_user.name)


@router.put("/{user_id}", response_model=User)
async def update_user(
    user_id: int,
    user: UserUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新用户（需要认证）"""
    db_user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="用户未找到")
    
    update_data = user.dict(exclude_unset=True)
    # 如果更新密码，需要加密
    if "password" in update_data:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
    
    # 更新字段
    for field, value in update_data.items():
        setattr(db_user, field, value)
    
    db.commit()
    db.refresh(db_user)
    
    return User(id=db_user.id, email=db_user.email, name=db_user.name)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除用户（需要认证）"""
    db_user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="用户未找到")
    
    db.delete(db_user)
    db.commit()
    return None

