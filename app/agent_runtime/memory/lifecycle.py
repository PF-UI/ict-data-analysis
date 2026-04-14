"""PostgreSQL 检查点生命周期：连接池、建表、编译 Graph。"""
from __future__ import annotations

import asyncio
from typing import Any

from app.agent_runtime.graphs.recruitment_react import compile_default_react_graph
from app.agent_runtime.mcp.client import load_tools_for_servers
from app.agent_runtime.runtime_state import (
    set_agent_memory_pool,
    set_compiled_graph,
)
from app.agent_runtime.skills.loader import load_skill
from app.core.config import settings

_PG_DEPS_HINT = (
    "当前 Python 环境未安装 langgraph-checkpoint-postgres（或 psycopg）。"
    "若刚用裸 pip 安装却出现本错误，多半是包装进了用户目录而非项目 .venv。"
    "请在项目根目录执行（Windows）: "
    '.\\.venv\\Scripts\\python.exe -m pip install "langgraph-checkpoint-postgres>=2,<4" "psycopg[pool]>=3.2" '
    "或运行: powershell -ExecutionPolicy Bypass -File scripts\\install_agent_memory_deps.ps1"
)

_PG_CONN_HINT = (
    "无法连接智能体记忆库 PostgreSQL（连接超时或目标不可达）。"
    "请确认本机已启动 PostgreSQL 且监听 .env 中的 DB_HOST/DB_PORT，账号密码与 DB_NAME 正确。"
    "若暂不启用记忆持久化，可在 .env 中注释或删除 DB_USER、DB_HOST、DB_NAME 中任意一项，使应用跳过记忆库初始化。"
)


async def init_agent_runtime() -> None:
    """在 FastAPI lifespan 中调用：配置记忆库则启用 AsyncPostgresSaver。"""
    pool: Any = None
    checkpointer: Any = None

    uri = (settings.get_agent_memory_database_url() or "").strip()
    if uri:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from psycopg import OperationalError as PsycopgOperationalError
            from psycopg.rows import dict_row
            from psycopg_pool import AsyncConnectionPool, PoolTimeout
        except ImportError as e:
            raise RuntimeError(_PG_DEPS_HINT) from e

        pool = AsyncConnectionPool(
            conninfo=uri,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
            open=False,
            max_size=settings.AGENT_MEMORY_POOL_MAX_SIZE,
        )
        try:
            await pool.open()
            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()
        except Exception as e:
            await pool.close()
            if isinstance(e, (PoolTimeout, PsycopgOperationalError)):
                raise RuntimeError(_PG_CONN_HINT) from e
            raise

    set_agent_memory_pool(pool)

    spec = load_skill(settings.DEFAULT_AGENT_SKILL)
    mcp_tools = await load_tools_for_servers(
        settings.mcp_servers_parsed(),
        spec.mcp_server_names,
    )
    graph = compile_default_react_graph(checkpointer=checkpointer, mcp_tools=mcp_tools)
    set_compiled_graph(graph)


async def shutdown_agent_runtime() -> None:
    from app.agent_runtime.runtime_state import get_connection_pool

    p = get_connection_pool()
    set_agent_memory_pool(None)
    set_compiled_graph(None)
    if p is not None:
        try:
            await p.close()
        except asyncio.CancelledError:
            pass
        except Exception:
            # reload / Ctrl+C 时池内后台建连可能仍在失败，不必再抛出
            pass
