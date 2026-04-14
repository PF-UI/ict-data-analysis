"""进程级 Agent 运行时：记忆库连接池与编译后的 Graph。"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from psycopg_pool import AsyncConnectionPool

_connection_pool: AsyncConnectionPool | None = None
_compiled_graph: CompiledStateGraph | None = None


def set_agent_memory_pool(pool: AsyncConnectionPool | None) -> None:
    global _connection_pool
    _connection_pool = pool


def get_connection_pool() -> AsyncConnectionPool | None:
    return _connection_pool


def set_compiled_graph(graph: CompiledStateGraph | None) -> None:
    global _compiled_graph
    _compiled_graph = graph


def get_compiled_graph() -> CompiledStateGraph:
    if _compiled_graph is None:
        raise RuntimeError(
            "Agent graph not initialized; call init_agent_runtime() on startup"
        )
    return _compiled_graph
