"""MCP 客户端骨架：当前返回空工具列表，避免阻塞启动。"""
from __future__ import annotations

from collections.abc import Sequence

from langchain_core.tools import BaseTool

from app.agent_runtime.mcp.config import MCPServerConfig


async def load_tools_for_servers(
    servers: Sequence[MCPServerConfig],
    requested_names: Sequence[str],
) -> list[BaseTool]:
    """按 skill 请求的 MCP 名过滤并加载工具。未实现具体传输时返回 []。"""
    if not servers or not requested_names:
        return []
    allowed = {s.name for s in servers}
    for name in requested_names:
        if name not in allowed:
            raise ValueError(f"MCP server not configured: {name}")
    # TODO: 使用 mcp SDK / langchain-mcp-adapters 连接并转为 BaseTool
    return []
