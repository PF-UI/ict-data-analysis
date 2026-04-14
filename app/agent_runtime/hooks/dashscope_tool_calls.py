"""通义/DashScope：保证 assistant 序列化时带 tool_calls 且 id 非空。"""
from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.content import create_tool_call

_KG_TOOL_NAME = "query_recruitment_knowledge_graph"
_READ_START_FRAG_RE = re.compile(
    r"(MATCH|OPTIONAL\s+MATCH|CALL|WITH|UNWIND|RETURN)\b",
    re.IGNORECASE,
)


def _trim_tool_call_json_leak(s: str) -> str:
    """去掉流式工具参数末尾误入的 JSON 引号/花括号，避免 Neo4j 报字符串引号不成对。"""
    s = s.rstrip()
    for _ in range(12):
        if not s:
            break
        if s.endswith('\\"}"'):
            s = s[:-4].rstrip()
            continue
        if s.endswith('\\"}'):
            s = s[:-3].rstrip()
            continue
        if s.endswith('"}'):
            s = s[:-2].rstrip()
            continue
        if s.endswith('}"'):
            s = s[:-2].rstrip()
            continue
        if s.endswith("\\"):
            s = s[:-1].rstrip()
            continue
        if s.endswith("}"):
            s = s[:-1].rstrip()
            continue
        if len(s) >= 2 and s[-1] == '"' and s[-2] in "0123456789":
            s = s[:-1].rstrip()
            continue
        if s.endswith('"') and s.count('"') % 2 == 1:
            s = s[:-1].rstrip()
            continue
        break
    return s


def _invalid_entry_as_dict(it: Any) -> dict[str, Any]:
    if isinstance(it, dict):
        return it
    md = getattr(it, "model_dump", None)
    if callable(md):
        try:
            d = md()
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return {
        "args": getattr(it, "args", None),
        "index": getattr(it, "index", None),
        "name": getattr(it, "name", None),
    }


def _neo4j_cypher_from_invalid_fragments(
    invalid: Any, *, prefix: str = ""
) -> str:
    """部分 OpenAI 兼容网关把工具参数流式拆成多条 InvalidToolCall（仅 args 为字符串碎片）。"""
    rows: list[tuple[tuple[int, int | str], str]] = []
    for it in invalid or []:
        d = _invalid_entry_as_dict(it)
        if (d.get("name") or "").strip():
            continue
        args = d.get("args")
        if args is None:
            continue
        frag = str(args)
        if not frag.strip() or frag.strip() in {'"', "'", '""'}:
            continue
        idx = d.get("index")
        if idx is None:
            sort_key: tuple[int, int | str] = (0, len(rows))
        else:
            try:
                sort_key = (0, int(idx))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                sort_key = (1, str(idx))
        rows.append((sort_key, frag))
    rows.sort(key=lambda x: x[0])
    fragments = [x[1] for x in rows]
    s = (prefix or "") + "".join(fragments)
    s = s.strip()
    s = _trim_tool_call_json_leak(s)
    if not s:
        return ""
    head = s.lstrip()
    if _READ_START_FRAG_RE.match(head):
        return s
    if s.startswith("("):
        return "MATCH " + s
    if ")" in s[:96] and not s.startswith("MATCH"):
        return "MATCH (" + s
    return "MATCH " + s


def _repair_neo4j_tool_args(
    args: dict[str, Any],
    invalid: Any,
    *,
    prefix: str = "",
) -> tuple[dict[str, Any], bool]:
    cq = args.get("cypher_query") if isinstance(args, dict) else None
    if isinstance(cq, str) and cq.strip():
        return args, False
    merged = _neo4j_cypher_from_invalid_fragments(invalid, prefix=prefix)
    if not merged:
        return args, False
    out = dict(args) if isinstance(args, dict) else {}
    out["cypher_query"] = merged
    return out, True


def _cypher_prefix_from_unnamed_tool_calls(merged: list[Any]) -> str:
    """无 name 的伪 tool_call 里常带 cypher_query 前缀（如 MATCH (），须与 invalid 碎片拼接。"""
    parts: list[str] = []
    for tc in merged:
        if isinstance(tc, dict):
            name, args, _ = _flatten_tool_call_dict(tc)
        else:
            name = (getattr(tc, "name", None) or "").strip()
            args = getattr(tc, "args", {}) or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except json.JSONDecodeError:
                    args = {}
            if not isinstance(args, dict):
                args = {}
        if name:
            continue
        cq = args.get("cypher_query") if isinstance(args, dict) else None
        if isinstance(cq, str) and cq:
            parts.append(cq)
    return "".join(parts)


def _tool_call_ids_from_ai(ai: AIMessage) -> set[str]:
    ids: set[str] = set()
    for tc in ai.tool_calls or []:
        if isinstance(tc, dict):
            tid = tc.get("id")
        else:
            tid = getattr(tc, "id", None)
        if tid is not None and str(tid):
            ids.add(str(tid))
    return ids


def _drop_incomplete_tool_round(out: list[BaseMessage]) -> None:
    """去掉未完成的工具轮次：尾部 ToolMessage + 最后一条带 tool_calls 的 AIMessage。"""
    while out and isinstance(out[-1], ToolMessage):
        out.pop()
    for i in range(len(out) - 1, -1, -1):
        if isinstance(out[i], AIMessage) and out[i].tool_calls:
            out[i] = out[i].model_copy(update={"tool_calls": []})
            break


def sanitize_messages_for_tool_chat(
    messages: Sequence[BaseMessage],
) -> list[BaseMessage]:
    """修复检查点恢复后可能出现的非法序列（如 tool 前无 tool_calls），满足上游通义等校验。

    仅用于构造发给 LLM 的 ``llm_input_messages``，不修改检查点内原始 ``messages``。
    """
    pending: set[str] = set()
    out: list[BaseMessage] = []

    for m in messages:
        if isinstance(m, AIMessage):
            out.append(m)
            pending = _tool_call_ids_from_ai(m)
        elif isinstance(m, ToolMessage):
            tid = str(m.tool_call_id) if m.tool_call_id is not None else ""
            if tid and tid in pending:
                out.append(m)
                pending.discard(tid)
        elif isinstance(m, (HumanMessage, SystemMessage)):
            if pending:
                _drop_incomplete_tool_round(out)
            out.append(m)
            pending.clear()
        else:
            if pending:
                _drop_incomplete_tool_round(out)
            out.append(m)
            pending.clear()

    if pending:
        _drop_incomplete_tool_round(out)

    return out


def pre_model_sanitize_llm_input(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph pre_model_hook：在调用 LLM 前生成干净的 ``llm_input_messages``。"""
    from app.agent_runtime.hooks.llm_io_log import log_llm_input_messages
    from app.agent_runtime.token_budget import truncate_llm_input_messages
    from app.core.config import settings

    raw = list(state.get("messages") or [])
    cleaned = sanitize_messages_for_tool_chat(raw)
    budget = settings.llm_max_prompt_tokens_for_model()
    divisor = settings.LLM_TOKEN_ESTIMATE_BYTES_DIVISOR
    capped = truncate_llm_input_messages(cleaned, budget, divisor)
    log_llm_input_messages(capped)
    return {"llm_input_messages": capped}


def _flatten_tool_call_dict(tc: dict[str, Any]) -> tuple[str, dict[str, Any], Any]:
    """从模型/网关可能返回的多种结构中提取 name、args、id。"""
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
            args = {"_raw": args}
    if not isinstance(args, dict):
        args = {}
    return name, args, tid


def tool_calls_from_content_blocks(content: Any) -> list[dict[str, Any]]:
    if not isinstance(content, list):
        return []
    out: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_call":
            continue
        name = block.get("name") or ""
        args = block.get("args", {})
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {}
        tid = block.get("id")
        out.append(create_tool_call(name=name, args=args, id=tid))
    return out


def _tc_signature(tc: Any) -> tuple[str, str, str] | None:
    """用于判断 tool_calls 是否仅需 noop，避免反复写回 messages 浪费图步数。"""
    if isinstance(tc, dict):
        name, args, tid = _flatten_tool_call_dict(tc)
        d = {"name": name, "args": args, "id": tid}
    elif hasattr(tc, "name") and hasattr(tc, "args"):
        d = {
            "name": getattr(tc, "name", "") or "",
            "args": getattr(tc, "args", {}) or {},
            "id": getattr(tc, "id", None),
        }
    else:
        return None
    name = (d.get("name") or "").strip()
    args = d.get("args") if "args" in d else {}
    if not isinstance(args, dict):
        args = {"_repr": str(args)}
    tid = str(d.get("id") or "")
    args_s = json.dumps(args, sort_keys=True, ensure_ascii=False)
    return (name, args_s, tid)


def _tool_calls_all_have_non_empty_ids(tool_calls: Any) -> bool:
    if not tool_calls:
        return True
    for tc in tool_calls:
        if isinstance(tc, dict):
            _, _, tid = _flatten_tool_call_dict(tc)
        else:
            tid = getattr(tc, "id", None)
        if tid is None or not str(tid).strip():
            return False
    return True


def _tool_calls_signatures(tool_calls: Any) -> list[tuple[str, str, str]]:
    if not tool_calls:
        return []
    out: list[tuple[str, str, str]] = []
    for tc in tool_calls:
        sig = _tc_signature(tc)
        if sig is not None and sig[0]:
            out.append(sig)
    return out


def strip_tool_call_blocks_from_content(content: Any) -> Any:
    if not isinstance(content, list):
        return content
    filtered = [
        b
        for b in content
        if not (isinstance(b, dict) and b.get("type") == "tool_call")
    ]
    if not filtered:
        return ""
    return filtered


def ensure_tool_call_ids(state: dict[str, Any]) -> dict[str, Any]:
    from app.agent_runtime.hooks.llm_io_log import log_llm_post_model_output
    from app.core.config import settings

    messages = state.get("messages") or []
    last_ai: AIMessage | None = None
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            last_ai = m
            break
    if last_ai is None:
        return {}

    if settings.AGENT_LLM_IO_LOG:
        log_llm_post_model_output(last_ai)

    merged: list[Any] = []
    if last_ai.tool_calls:
        for tc in last_ai.tool_calls:
            if isinstance(tc, dict):
                merged.append(dict(tc))
            else:
                merged.append(tc)  # type: ignore[arg-type]
    if not merged:
        merged = tool_calls_from_content_blocks(last_ai.content)

    if not merged:
        return {}

    cq_prefix = _cypher_prefix_from_unnamed_tool_calls(merged)
    new_calls: list[dict[str, Any]] = []
    stripped_invalid_because_repaired = False
    for tc in merged:
        if isinstance(tc, dict):
            name, args, tid = _flatten_tool_call_dict(tc)
        else:
            name = (getattr(tc, "name", None) or "").strip()
            args = getattr(tc, "args", {}) or {}
            tid = getattr(tc, "id", None)
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except json.JSONDecodeError:
                    args = {}
            if not isinstance(args, dict):
                args = {}
        if not name:
            continue
        if name == _KG_TOOL_NAME:
            args, did = _repair_neo4j_tool_args(
                args,
                last_ai.invalid_tool_calls,
                prefix=cq_prefix,
            )
            if did:
                stripped_invalid_because_repaired = True
            cq_prefix = ""
        tid = tid or str(uuid4())
        new_calls.append(
            {"name": name, "args": args, "id": str(tid), "type": "tool_call"}
        )

    if not new_calls:
        # 模型返回了无法执行的 tool（如空函数名），清掉 tool_calls 避免路由在 pending 上空转
        if merged:
            stripped = strip_tool_call_blocks_from_content(last_ai.content)
            upd: dict[str, Any] = {"tool_calls": []}
            if stripped != last_ai.content:
                upd["content"] = stripped
            return {"messages": [last_ai.model_copy(update=upd)]}
        return {}

    new_content = strip_tool_call_blocks_from_content(last_ai.content)
    # 语义未变则不要写回 messages；但若原始 tool_calls 缺 id，LangGraph 会在 ToolMessage 处报错，禁止 noop
    old_sigs = _tool_calls_signatures(last_ai.tool_calls)
    new_sigs = _tool_calls_signatures(new_calls)
    if (
        new_sigs == old_sigs
        and new_content == last_ai.content
        and _tool_calls_all_have_non_empty_ids(last_ai.tool_calls)
    ):
        return {}

    updates: dict[str, Any] = {"tool_calls": new_calls}
    if new_content != last_ai.content:
        updates["content"] = new_content
    if stripped_invalid_because_repaired:
        updates["invalid_tool_calls"] = []
    fixed = last_ai.model_copy(update=updates)
    return {"messages": [fixed]}
