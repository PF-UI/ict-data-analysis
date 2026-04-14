"""按 Skill 解析原生工具 + MCP 工具列表。"""
from __future__ import annotations

from collections.abc import Sequence

from langchain_core.tools import BaseTool

from app.agent_runtime.skills.schema import SkillSpec
from app.agent_runtime.tools.neo4j_tool import query_recruitment_knowledge_graph

_NATIVE_REGISTRY: dict[str, BaseTool] = {
    "neo4j_cypher": query_recruitment_knowledge_graph,
}


def resolve_native_tools(names: Sequence[str]) -> list[BaseTool]:
    out: list[BaseTool] = []
    for name in names:
        if name not in _NATIVE_REGISTRY:
            raise KeyError(f"Unknown native tool: {name}")
        out.append(_NATIVE_REGISTRY[name])
    return out


def tools_for_skill(spec: SkillSpec, mcp_tools: Sequence[BaseTool] | None = None) -> list[BaseTool]:
    tools = resolve_native_tools(spec.native_tools)
    if mcp_tools:
        tools = [*tools, *mcp_tools]
    return tools
