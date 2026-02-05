"""
FastAPI应用主文件
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import api_router
from app.database import init_db
# 导入模型以确保表被创建
from app.models import User, JobListing, CityMapping

# 创建FastAPI应用实例
app = FastAPI(
    title="FastAPI 应用",
    description="一个基于FastAPI的Web应用",
    version="1.0.0",
)


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库"""
    try:
        init_db()
        print("✅ 数据库初始化成功")
    except Exception as e:
        print(f"⚠️ 数据库初始化失败: {e}")
        print("⚠️ 应用将继续运行，但数据库功能可能不可用")
        print("⚠️ 请检查 .env 文件中的 DATABASE_URL 配置")
        print("⚠️ 可以运行 'python test.py' 测试数据库连接")

# 配置CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中应该设置具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 包含路由
app.include_router(api_router, prefix="/api/v1", tags=["api"])


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "欢迎使用FastAPI应用",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy"}

