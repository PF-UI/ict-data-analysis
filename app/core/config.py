"""
应用配置
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path
from dotenv import load_dotenv


# 加载 .env 文件中的环境变量
project_root = Path(__file__).parent.parent.parent  # 项目根目录
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)

class Settings(BaseSettings):
    """应用设置"""
    # JWT配置
    SECRET_KEY: str = Field(
        default="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7",
        description="JWT密钥"
    )
    ALGORITHM: str = Field(default="HS256", description="JWT算法")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="访问令牌过期时间（分钟）")
    
    # 数据库配置（MySQL）
    # 默认配置与 test.py 中的配置保持一致
    DATABASE_URL: str = Field(
        default="mysql+pymysql://root:pf123456@127.0.0.1:3306/zpsj",
        description="数据库连接URL"
    )
    DB_POOL_SIZE: int = Field(default=5, description="数据库连接池大小")
    DB_MAX_OVERFLOW: int = Field(default=10, description="数据库连接池最大溢出数")
    DB_POOL_RECYCLE: int = Field(default=3600, description="数据库连接池回收时间（秒）")
    
    model_config = SettingsConfigDict(
        env_file=str(env_path),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # 忽略 .env 文件中未定义的字段
    )


settings = Settings()