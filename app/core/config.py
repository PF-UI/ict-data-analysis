"""
应用配置

业务数据默认使用 MySQL（DATABASE_URL）。智能体多轮对话状态使用独立 PostgreSQL
（AGENT_MEMORY_DATABASE_URL），与业务库分离。
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# 加载 .env 文件中的环境变量
project_root = Path(__file__).parent.parent.parent  # 项目根目录
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)


class Settings(BaseSettings):
    """应用设置"""

    # JWT配置
    SECRET_KEY: str = Field(
        default="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7",
        description="JWT密钥",
    )
    ALGORITHM: str = Field(default="HS256", description="JWT算法")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30, description="访问令牌过期时间（分钟）"
    )
    BACKEND_CORS_ORIGINS: str = Field(
        default="*",
        description=(
            "CORS 允许的 Origin，逗号分隔多个 URL；"
            "开发可用 *；生产建议设为前端公网地址（如 https://example.com）"
        ),
    )

    # 数据库配置（MySQL，业务 ORM）
    DATABASE_URL: str = Field(
        default="mysql+pymysql://root:pf123456@127.0.0.1:3306/zpsj",
        description="业务库连接 URL（MySQL）",
    )
    DB_POOL_SIZE: int = Field(default=5, description="数据库连接池大小")
    DB_MAX_OVERFLOW: int = Field(default=10, description="数据库连接池最大溢出数")
    DB_POOL_RECYCLE: int = Field(default=3600, description="数据库连接池回收时间（秒）")

    # LLM（与根目录历史环境变量对齐）
    LLM_MODEL: str = Field(default="qwen3-max", description="对话模型名")
    LLM_API_KEY: str | None = Field(default=None, description="LLM API Key")
    OPENAI_BASE_URL: str = Field(
        default="http://localhost:3000/v1",
        description="OpenAI 兼容网关 Base URL",
    )
    LLM_TEMPERATURE: float = Field(default=0.0, description="采样温度")
    # 模型上下文与限流相关预算（默认对齐豆包类 256K 窗口；RPM/TPM 由网关侧落实为主）
    LLM_CONTEXT_WINDOW_TOKENS: int = Field(
        default=262_144, description="上下文长度（tokens，约 256K）"
    )
    LLM_MAX_INPUT_TOKENS_PER_TURN: int = Field(
        default=258_048, description="单轮最大输入（tokens，约 252K）"
    )
    LLM_MAX_OUTPUT_TOKENS: int = Field(
        default=65_536, description="最大输出长度（tokens，约 64K）"
    )
    LLM_MAX_OUTPUT_THINKING_TOKENS: int = Field(
        default=32_768, description="思考模式下最大输出（tokens，约 32K）"
    )
    LLM_MAX_REASONING_TOKENS: int = Field(
        default=81_920, description="最大思维链长度（tokens，约 80K），供扩展 API 使用"
    )
    LLM_PROMPT_OVERHEAD_TOKENS: int = Field(
        default=8192,
        description="为系统提示与工具描述等预留的 token 估算余量",
    )
    LLM_THINKING_MODE: bool = Field(
        default=False, description="是否按思考模式使用更小的 max_tokens"
    )
    LLM_TOKEN_ESTIMATE_BYTES_DIVISOR: float = Field(
        default=3.0,
        description="token 粗估：UTF-8 字节数除以该值（中英混排偏保守）",
    )

    # PostgreSQL（与 .env 中 DB_* 对齐，供智能体记忆库默认连接）
    DB_USER: str | None = Field(default=None, description="PostgreSQL 用户名")
    DB_PASSWORD: str | None = Field(default=None, description="PostgreSQL 密码")
    DB_HOST: str | None = Field(default=None, description="PostgreSQL 主机")
    DB_PORT: int = Field(default=5432, description="PostgreSQL 端口")
    DB_NAME: str | None = Field(default=None, description="PostgreSQL 数据库名")
    DB_URI: str | None = Field(
        default=None,
        description="完整 postgresql:// 连接串；若含 {占位符} 则忽略并改用 DB_* 拼接",
    )
    PG_SSLMODE: str = Field(
        default="disable",
        description="记忆库连接串 query参数 sslmode",
    )

    # 智能体记忆库（PostgreSQL only，langgraph-checkpoint-postgres）
    AGENT_MEMORY_DATABASE_URL: str | None = Field(
        default=None,
        description="显式覆盖记忆库 URL；未设时依次尝试 DB_URI（字面量）、DB_* 拼接",
    )
    AGENT_MEMORY_POOL_MAX_SIZE: int = Field(
        default=10, description="记忆库异步连接池最大连接数"
    )
    DEFAULT_AGENT_SKILL: str = Field(
        default="recruitment_qa", description="默认 Skill ID（对应 skills目录下 yaml）"
    )
    AGENT_RECURSION_LIMIT: int = Field(
        default=160,
        ge=40,
        le=500,
        description=(
            "LangGraph 图执行步数上限。create_react_agent v2 下每轮含 pre_model、agent、post_model、"
            "按 tool_call 拆分的 tools 等，易占 10～30+ 步；多轮工具或重试时 64 往往不够。"
            "若 .env 曾设 64 请删除或改大。仍顶满请查模型是否反复调工具。"
        ),
    )
    QA_MAX_KG_TOOL_INVOCATIONS_PER_TURN: int = Field(
        default=5,
        ge=1,
        le=30,
        description=(
            "自本轮用户提问以来，图谱工具 **实际访问 Neo4j（execute）** 的最多次数；"
            "预检拦截、重复查询、仅返回系统提示等不计入，避免无效重试占满额度。"
            "达到后本回合不再执行读库。"
        ),
    )
    QA_MAX_KG_TOOL_MESSAGES_HARD_CAP: int = Field(
        default=12,
        ge=4,
        le=60,
        description=(
            "本轮用户消息以来，图谱工具任意返回（含预检/重复/限流）的 ToolMessage 条数硬上限，"
            "防止模型空转；应大于 QA_MAX_KG_TOOL_INVOCATIONS_PER_TURN。"
        ),
    )
    QA_MAX_KG_TOOL_PREFLIGHT_ERRORS_PER_TURN: int = Field(
        default=2,
        ge=1,
        le=30,
        description=(
            "自本轮用户提问以来，图谱工具返回为【参数错误】/【语法预检】/【安全拒绝】的累计次数上限；"
            "达到后再调用将直接返回【系统限制】，不进入 Cypher 预检与读库。应小于或等于 QA_MAX_KG_TOOL_MESSAGES_HARD_CAP。"
        ),
    )
    QA_KG_TOOL_VERBOSE_LOG: bool = Field(
        default=False,
        description=(
            "为 true 时图谱查询工具输出 DEBUG 级详情：完整 Cypher（有上限）、Neo4j 耗时、"
            "异常堆栈；INFO 级仍会输出结构化摘要，便于排查系统限制与重试原因。"
        ),
    )
    AGENT_LLM_IO_LOG: bool = Field(
        default=False,
        description=(
            "为 true 时在 pre_model / post_model 钩子打印发往 LLM 的消息摘要与模型返回的 "
            "AIMessage（含 tool_calls、invalid_tool_calls），便于判断空参数来自模型还是绑定环节。"
            "日志为 INFO，键名 agent_llm；勿在生产长期开启。"
        ),
    )
    AGENT_LLM_IO_PREVIEW_CHARS: int = Field(
        default=1200,
        ge=200,
        le=32_000,
        description="AGENT_LLM_IO_LOG 为 true 时，每条消息 content 预览最大字符数。",
    )
    MCP_SERVERS_JSON: str = Field(
        default="",
        description='可选：MCP 服务 JSON 数组，元素字段见 app.agent_runtime.mcp.config.MCPServerConfig',
    )

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
    )

    def mcp_servers_parsed(self) -> list:
        from app.agent_runtime.mcp.config import MCPServerConfig

        raw = (self.MCP_SERVERS_JSON or "").strip()
        if not raw:
            return []
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("MCP_SERVERS_JSON 必须是 JSON 数组")
        return [MCPServerConfig.model_validate(item) for item in data]

    def get_agent_memory_database_url(self) -> str | None:
        """解析智能体记忆库 PostgreSQL 连接串。"""
        explicit = (self.AGENT_MEMORY_DATABASE_URL or "").strip()
        if explicit:
            return explicit
        raw_uri = (self.DB_URI or "").strip()
        if raw_uri and "{" not in raw_uri:
            return raw_uri
        user = (self.DB_USER or "").strip()
        host = (self.DB_HOST or "").strip()
        name = (self.DB_NAME or "").strip()
        if user and host and name:
            pwd = self.DB_PASSWORD or ""
            u = quote_plus(user)
            p = quote_plus(pwd)
            sslmode = (self.PG_SSLMODE or "disable").strip() or "disable"
            return (
                f"postgresql://{u}:{p}@{host}:{self.DB_PORT}/{name}?sslmode={sslmode}"
            )
        return None

    def llm_effective_max_output_tokens(self) -> int:
        """当前配置下传给 Chat Completions 的 max_tokens 上限。"""
        if self.LLM_THINKING_MODE:
            return min(self.LLM_MAX_OUTPUT_THINKING_TOKENS, self.LLM_MAX_OUTPUT_TOKENS)
        return self.LLM_MAX_OUTPUT_TOKENS

    def llm_max_prompt_tokens_for_model(self) -> int:
        """发给模型的多轮消息总 token 粗估上限（窗口减输出余量）。"""
        reserve = self.llm_effective_max_output_tokens() + self.LLM_PROMPT_OVERHEAD_TOKENS
        return max(4096, self.LLM_CONTEXT_WINDOW_TOKENS - reserve)


settings = Settings()