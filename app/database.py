"""
数据库连接和会话管理
"""
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from app.core.config import settings

# 获取数据库连接URL
database_url = settings.DATABASE_URL

# 创建数据库引擎
# 对于SQLite，需要设置check_same_thread=False
# 对于MySQL，使用默认配置即可
connect_args = {}
if database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif database_url.startswith("mysql"):
    # MySQL 配置，与 test.py 中的配置保持一致
    connect_args = {
        "charset": "utf8mb4",  # 推荐使用utf8mb4，兼容所有Unicode字符（包括emoji）
        "connect_timeout": 10
    }

engine = create_engine(
    database_url,
    connect_args=connect_args,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,  # 连接前测试连接，自动重连断开的连接
    echo=False,  # 设置为True可以看到SQL日志
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基础模型类
Base = declarative_base()


def get_db():
    """
    数据库会话依赖注入
    用于FastAPI的依赖注入系统
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库，创建所有表"""
    try:
        # 测试连接
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        # 创建所有表
        Base.metadata.create_all(bind=engine)
        print("✅ 数据库表初始化成功")
    except OperationalError as e:
        error_msg = str(e)
        if "1045" in error_msg or "Access denied" in error_msg:
            raise OperationalError(
                "数据库连接失败：用户名或密码错误。请检查 .env 文件中的 DATABASE_URL 配置。",
                None,
                None
            ) from e
        elif "1049" in error_msg or "Unknown database" in error_msg:
            raise OperationalError(
                "数据库不存在。请先创建数据库。",
                None,
                None
            ) from e
        elif "2003" in error_msg or "Can't connect" in error_msg:
            raise OperationalError(
                "无法连接到 MySQL 服务器。请检查 MySQL 服务是否运行。",
                None,
                None
            ) from e
        else:
            raise