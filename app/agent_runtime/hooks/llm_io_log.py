"""可选：打印本轮发往 LLM 的消息与模型返回的 AIMessage，用于定位工具参数丢失等环节。"""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def _thread_id() -> str:
    try:
        from langgraph.config import get_config

        cfg = get_config() or {}
        tid = (cfg.get("configurable") or {}).get("thread_id")
        return str(tid) if tid is not None else ""
    except Exception:
        return ""


def _preview(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + f"…[共 {len(s)} 字符]"


def _content_to_text(content: Any) -> str:
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
                t = block.get("type")
                if t == "text":
                    parts.append(str(block.get("text") or ""))
                elif t == "tool_call":
                    parts.append(f"[tool_call block name={block.get('name')}]")
                else:
                    try:
                        parts.append(json.dumps(block, ensure_ascii=False)[:400])
                    except Exception:
                        parts.append(str(block)[:400])
        return "\n".join(parts)
    return str(content)


def _flatten_tool_call_for_log(tc: Any) -> tuple[str, dict[str, Any], str]:
    if isinstance(tc, dict):
        tid = tc.get("id")
        if tid is None:
            tid = tc.get("tool_call_id")
        args = tc.get("args") if "args" in tc else tc.get("arguments")
        name = (tc.get("name") or "").strip()
        fn = tc.get("function")
        if isinstance(fn, dict):
            name = (name or (fn.get("name") or "")).strip()
            if args is None:
                args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {"_raw": _preview(args, 800)}
        if not isinstance(args, dict):
            args = {"_repr": _preview(str(args), 800)}
        return name, args, str(tid) if tid is not None else ""
    name = (getattr(tc, "name", None) or "").strip()
    args = getattr(tc, "args", None) or {}
    tid = getattr(tc, "id", None)
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            args = {"_raw": _preview(args, 800)}
    if not isinstance(args, dict):
        args = {"_repr": _preview(str(args), 800)}
    return name, args, str(tid) if tid is not None else ""


def _args_for_log(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "query_recruitment_knowledge_graph":
        cq = args.get("cypher_query")
        if isinstance(cq, str):
            return {
                **{k: v for k, v in args.items() if k != "cypher_query"},
                "cypher_query": _preview(
                    cq, min(4000, settings.AGENT_LLM_IO_PREVIEW_CHARS)
                ),
                "cypher_query_empty": not cq.strip(),
            }
    try:
        s = json.dumps(args, ensure_ascii=False)
        if len(s) > 1200:
            return {"_preview": _preview(s, 1200)}
        return dict(args)
    except Exception:
        return {"_repr": _preview(str(args), 1200)}


def _serialize_tool_calls(tool_calls: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tc in tool_calls or []:
        name, args, tid = _flatten_tool_call_for_log(tc)
        out.append(
            {
                "name": name,
                "id": tid,
                "args": _args_for_log(name, args),
            }
        )
    return out


def _message_row(m: BaseMessage, idx: int, preview_limit: int) -> dict[str, Any]:
    row: dict[str, Any] = {"i": idx, "role": m.type}
    text = _content_to_text(getattr(m, "content", None))
    row["content_preview"] = _preview(text, preview_limit)
    if isinstance(m, AIMessage):
        row["tool_calls"] = _serialize_tool_calls(m.tool_calls)
        inv = getattr(m, "invalid_tool_calls", None) or []
        if inv:
            row["invalid_tool_calls"] = [
                _preview(json.dumps(x, ensure_ascii=False, default=str), 600)
                if not isinstance(x, str)
                else _preview(x, 600)
                for x in inv[:8]
            ]
    if isinstance(m, ToolMessage):
        row["tool_name"] = getattr(m, "name", None) or ""
        row["tool_call_id"] = str(getattr(m, "tool_call_id", "") or "")
    return row


def log_llm_input_messages(messages: list[BaseMessage] | None) -> None:
    if not settings.AGENT_LLM_IO_LOG:
        return
    msgs = list(messages or [])
    lim = settings.AGENT_LLM_IO_PREVIEW_CHARS
    tail_n = min(24, len(msgs))
    tail = msgs[-tail_n:] if tail_n else []
    payload = {
        "event": "llm_input",
        "thread_id": _thread_id(),
        "message_count": len(msgs),
        "tail_rendered": len(tail),
        "messages": [_message_row(m, len(msgs) - tail_n + i, lim) for i, m in enumerate(tail)],
    }
    try:
        logger.info("agent_llm %s", json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        logger.info("agent_llm llm_input thread_id=%s count=%s", _thread_id(), len(msgs))


def log_llm_post_model_output(last_ai: AIMessage) -> None:
    if not settings.AGENT_LLM_IO_LOG:
        return
    lim = settings.AGENT_LLM_IO_PREVIEW_CHARS
    text = _content_to_text(last_ai.content)
    payload = {
        "event": "llm_output",
        "thread_id": _thread_id(),
        "content_preview": _preview(text, lim),
        "tool_calls": _serialize_tool_calls(last_ai.tool_calls),
        "tool_calls_from_content": _serialize_tool_calls(
            [
                {"name": b.get("name"), "args": b.get("args"), "id": b.get("id")}
                for b in (last_ai.content if isinstance(last_ai.content, list) else [])
                if isinstance(b, dict) and b.get("type") == "tool_call"
            ]
        ),
    }
    inv = getattr(last_ai, "invalid_tool_calls", None) or []
    if inv:
        payload["invalid_tool_calls_count"] = len(inv)
        payload["invalid_tool_calls_preview"] = [
            _preview(json.dumps(x, ensure_ascii=False, default=str), 800)
            if not isinstance(x, str)
            else _preview(x, 800)
            for x in inv[:5]
        ]
    try:
        logger.info("agent_llm %s", json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        logger.info("agent_llm llm_output thread_id=%s", _thread_id())
