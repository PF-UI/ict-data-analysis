"""MCP 服务端点配置（骨架，供后续接入 langchain-mcp-adapters 等）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    """单台 MCP 服务声明。"""

    name: str = Field(description="逻辑名，与 skill.mcp_server_names 对应")
    transport: str = Field(default="stdio", description="stdio | sse（预留）")
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = Field(default=None, description="SSE/HTTP 基址（预留）")
