"""招聘问答 ReAct Graph：Skill + Model + Tools + 可选 Postgres checkpointer。"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.prebuilt import create_react_agent

from app.agent_runtime.hooks.dashscope_tool_calls import (
    ensure_tool_call_ids,
    pre_model_sanitize_llm_input,
)
from app.agent_runtime.model_factory import build_chat_model
from app.agent_runtime.prompts import load_prompt_text
from app.agent_runtime.skills.loader import load_skill
from app.agent_runtime.tools.registry import tools_for_skill
from app.core.config import settings


def compile_default_react_graph(
    *,
    checkpointer: BaseCheckpointSaver | None,
    skill_id: str | None = None,
    mcp_tools: list[BaseTool] | None = None,
) -> Any:
    sid = skill_id or settings.DEFAULT_AGENT_SKILL
    spec = load_skill(sid)
    system_prompt = load_prompt_text(spec.system_prompt)
    tools = tools_for_skill(spec, mcp_tools or [])
    llm = build_chat_model(
        model=spec.model,
        temperature=spec.temperature,
        max_tokens=settings.llm_effective_max_output_tokens(),
    )
    return create_react_agent(
        llm,
        tools=tools,
        prompt=system_prompt,
        pre_model_hook=pre_model_sanitize_llm_input,
        post_model_hook=ensure_tool_call_ids,
        checkpointer=checkpointer,
    )
