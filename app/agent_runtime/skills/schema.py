"""Skill 声明：组合提示词、原生工具与 MCP。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SkillSpec(BaseModel):
    id: str
    system_prompt: str = Field(
        description="prompts 包内文本名（不含 .txt）",
    )
    native_tools: list[str] = Field(default_factory=list)
    mcp_server_names: list[str] = Field(default_factory=list)
    model: str | None = None
    temperature: float | None = None
