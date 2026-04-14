"""
FastAPI应用主文件
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.logging_setup import ensure_app_package_logging
from fastapi.middleware.cors import CORSMiddleware

from app.agent_runtime.memory.lifecycle import init_agent_runtime, shutdown_agent_runtime
from app.core.config import settings
from app.database import init_db
from app.routers import api_router


def _cors_allow_origins() -> list[str]:
    raw = settings.BACKEND_CORS_ORIGINS.strip()
    if not raw or raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()] or ["*"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化业务库与 Agent 运行时；关闭时释放记忆库连接池。"""
    ensure_app_package_logging()
    try:
        init_db()
    except Exception as e:
        print(f"数据库初始化失败: {e}")
        print("请检查 .env：DATABASE_URL（MySQL）；AGENT_MEMORY_DATABASE_URL 或 DB_*（PostgreSQL）。")
        print("可以运行 'python test.py' 测试 MySQL 连接。")
        raise
    await init_agent_runtime()
    try:
        yield
    finally:
        try:
            await shutdown_agent_runtime()
        except asyncio.CancelledError:
            pass
        except Exception:
            # uvicorn --reload 时 lifespan 收尾可能与其它取消交织，忽略即可
            pass


# 创建FastAPI应用实例
app = FastAPI(
    title="FastAPI 应用",
    description="一个基于FastAPI的Web应用",
    version="1.0.0",
    lifespan=lifespan,
)

# 配置CORS中间件（生产在 .env 中设置 BACKEND_CORS_ORIGINS，逗号分隔）
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
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
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy"}
