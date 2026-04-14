"""流式输出：供 WebSocket 等调用。"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage

from app.agent_runtime.runtime_state import get_compiled_graph
from app.core.config import settings


def text_from_chat_chunk(chunk) -> str:
    content = getattr(chunk, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


def _sanitize_tool_input_preview(name: str | None, inp: Any) -> dict[str, Any]:
    """仅向前端暴露安全、简短的工具入参摘要。"""
    if not isinstance(inp, dict):
        return {}
    out: dict[str, Any] = {"tool": name or ""}
    if name == "query_recruitment_knowledge_graph":
        cq = inp.get("cypher_query")
        if isinstance(cq, str) and cq.strip():
            out["cypher_preview"] = cq.strip()[:240]
    else:
        keys = [k for k in inp.keys() if k != "state"][:6]
        out["arg_keys"] = keys
    return out


def _tool_output_preview(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        s = output
    else:
        s = str(output)
    s = s.strip()
    if len(s) > 400:
        return s[:400] + "…"
    return s


async def stream_agent_qa_payloads(
    question: str,
    *,
    thread_id: str,
) -> AsyncIterator[dict[str, Any]]:
    """流式输出统一事件：chunk（模型文本）与 tool_start/tool_end/tool_error（工具诊断）。"""
    agent = get_compiled_graph()
    state = {"messages": [HumanMessage(content=question)]}
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": settings.AGENT_RECURSION_LIMIT,
    }
    async for event in agent.astream_events(state, config=config, version="v2"):
        et = event.get("event")
        if et == "on_chat_model_stream":
            data = event.get("data") or {}
            chunk = data.get("chunk")
            if chunk is None:
                continue
            text = text_from_chat_chunk(chunk)
            if text:
                yield {"type": "chunk", "content": text}
            continue
        if et == "on_tool_start":
            name = event.get("name")
            inp = (event.get("data") or {}).get("input")
            yield {
                "type": "tool_start",
                "name": name,
                "input": _sanitize_tool_input_preview(
                    name if isinstance(name, str) else None, inp
                ),
            }
            continue
        if et == "on_tool_end":
            name = event.get("name")
            data = event.get("data") or {}
            yield {
                "type": "tool_end",
                "name": name,
                "output_preview": _tool_output_preview(data.get("output")),
            }
            continue
        if et == "on_tool_error":
            name = event.get("name")
            data = event.get("data") or {}
            err = data.get("error")
            yield {
                "type": "tool_error",
                "name": name,
                "error": repr(err) if err is not None else "",
            }
            continue


async def stream_agent_answer(
    question: str,
    *,
    thread_id: str,
) -> AsyncIterator[str]:
    """按 LLM 流式 token 输出助手回复文本片段（兼容旧接口，不含工具事件）。"""
    async for payload in stream_agent_qa_payloads(
        question, thread_id=thread_id
    ):
        if payload.get("type") == "chunk":
            c = payload.get("content") or ""
            if c:
                yield c
