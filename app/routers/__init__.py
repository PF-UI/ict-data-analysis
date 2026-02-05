"""
路由模块
"""
from fastapi import APIRouter
from app.routers import users, auth, job_listings, qa

# 创建主路由
api_router = APIRouter()

# 包含子路由
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(job_listings.router, prefix="/job-listings", tags=["job-listings"])
api_router.include_router(qa.router, prefix="/qa", tags=["qa"])

