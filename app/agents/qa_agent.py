"""
招聘问答智能体兼容层：实现已迁移至 app.agent_runtime。
"""
from __future__ import annotations

from app.agent_runtime.hooks.dashscope_tool_calls import ensure_tool_call_ids
from app.agent_runtime.prompts import load_prompt_text
from app.agent_runtime.runtime_state import get_compiled_graph
from app.agent_runtime.streaming import (
    stream_agent_answer,
    stream_agent_qa_payloads,
    text_from_chat_chunk,
)
from app.agent_runtime.tools.neo4j_tool import query_recruitment_knowledge_graph

SYSTEM_PROMPT = load_prompt_text("recruitment_qa_system")

__all__ = [
    "SYSTEM_PROMPT",
    "ensure_tool_call_ids",
    "get_qa_agent",
    "query_recruitment_knowledge_graph",
    "stream_agent_answer",
    "stream_agent_qa_payloads",
    "text_from_chat_chunk",
]


def get_qa_agent():
    """返回已编译的 LangGraph（需在应用 lifespan 中完成 init_agent_runtime）。"""
    return get_compiled_graph()
