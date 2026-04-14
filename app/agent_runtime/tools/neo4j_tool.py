"""招聘知识图谱只读 Cypher 工具（LangGraph ToolNode）。

不使用 ``from __future__ import annotations``：LangChain StructuredTool 依赖``inspect.signature`` 上的实类型注解，以便识别 ``InjectedState`` / ``InjectedToolCallId``。
"""
import hashlib
import json
import logging
import re
import time
from collections import deque
from typing import Annotated, Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field, model_validator

from app.agent_runtime.hooks.dashscope_tool_calls import (
    _flatten_tool_call_dict,
    _trim_tool_call_json_leak,
)
from app.core.config import settings
from app.services.neo4j_service import Neo4jReadOnlyService

logger = logging.getLogger(__name__)

MAX_TOOL_RESULT_CHARS = 12_000
_KG_TOOL_NAME = "query_recruitment_knowledge_graph"
_CYPHER_DEDUPE_EMPTY_KEY = "__kg_cypher_empty__"

_READ_START_RE = re.compile(
    r"\b(MATCH|OPTIONAL\s+MATCH|CALL|WITH|UNWIND|RETURN)\b",
    re.IGNORECASE | re.DOTALL,
)
_FORBIDDEN_WRITE_RE = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|REMOVE|SET|DROP|ALTER|FOREACH)\b",
    re.IGNORECASE,
)


def _runtime_thread_id() -> str:
    try:
        from langgraph.config import get_config

        cfg = get_config() or {}
        tid = (cfg.get("configurable") or {}).get("thread_id")
        return str(tid) if tid is not None else ""
    except Exception:
        return ""


def _norm_fingerprint(norm: str) -> str:
    if not norm:
        return ""
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _log_kg_event(branch: str, **fields: Any) -> None:
    payload: dict[str, Any] = {"event": branch, "thread_id": _runtime_thread_id()}
    for k, v in fields.items():
        if v is None:
            continue
        if isinstance(v, (list, dict, str, int, float, bool)):
            payload[k] = v
    try:
        logger.info("kg_tool %s", json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        logger.info("kg_tool event=%s thread_id=%s", branch, payload.get("thread_id"))


def _log_kg_verbose_cypher(cypher: str) -> None:
    if not settings.QA_KG_TOOL_VERBOSE_LOG:
        return
    limit = 8000
    s = cypher or ""
    if len(s) > limit:
        s = s[:limit] + f"\n... [cypher 已截断，共 {len(cypher)} 字符]"
    logger.debug("kg_tool cypher_full thread_id=%s\n%s", _runtime_thread_id(), s)


def _coerce_tool_call_to_dict(tc: Any) -> dict[str, Any] | None:
    if tc is None:
        return None
    if isinstance(tc, dict):
        return tc
    md = getattr(tc, "model_dump", None)
    if callable(md):
        try:
            d = md()
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    name = getattr(tc, "name", None)
    args = getattr(tc, "args", None)
    tid = getattr(tc, "id", None)
    if name is not None or args is not None or tid is not None:
        return {"name": name, "args": args, "id": tid}
    return None


def _args_dict_to_cypher(args: Any) -> str:
    if args is None:
        return ""
    try:
        parsed = _Neo4jQueryArgs.model_validate(
            {"cypher_query": args} if not isinstance(args, dict) else args
        )
        return (parsed.cypher_query or "").strip()
    except Exception:
        return ""


def _recover_cypher_from_ai_tool_calls(
    messages: Any, tool_call_id: str
) -> tuple[str, str]:
    if not isinstance(messages, list) or not (tool_call_id or "").strip():
        return "", ""
    tid = str(tool_call_id).strip()
    for m in reversed(messages):
        if not isinstance(m, AIMessage) or not getattr(m, "tool_calls", None):
            continue
        for tc in m.tool_calls:
            raw = _coerce_tool_call_to_dict(tc)
            if not raw:
                continue
            name, args, tcid = _flatten_tool_call_dict(raw)
            if name != _KG_TOOL_NAME:
                continue
            if str(tcid or "").strip() != tid:
                continue
            cq = _args_dict_to_cypher(args)
            if cq:
                return cq, "matched_tool_call_id"
            return "", "matched_tool_call_id_empty_args"
    return "", "no_matching_tool_call"


def _recover_cypher_fallback_last_ai(messages: Any) -> tuple[str, str]:
    if not isinstance(messages, list):
        return "", ""
    for m in reversed(messages):
        if not isinstance(m, AIMessage) or not getattr(m, "tool_calls", None):
            continue
        neo_items: list[Any] = []
        for tc in m.tool_calls:
            raw = _coerce_tool_call_to_dict(tc)
            if not raw:
                continue
            name, args, _tid = _flatten_tool_call_dict(raw)
            if name != _KG_TOOL_NAME:
                continue
            neo_items.append(args)
        if not neo_items:
            break
        if len(neo_items) > 1:
            return "", "fallback_skipped_multi_neo4j"
        cq = _args_dict_to_cypher(neo_items[0])
        if cq:
            return cq, "last_ai_neo4j_non_empty"
        return "", "last_ai_neo4j_single_but_empty_args"
    return "", ""


def _diag_neo4j_tool_calls_in_messages(messages: Any) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    for m in reversed(messages):
        if not isinstance(m, AIMessage) or not getattr(m, "tool_calls", None):
            continue
        out: list[dict[str, Any]] = []
        for tc in m.tool_calls:
            raw = _coerce_tool_call_to_dict(tc)
            if not raw:
                continue
            name, args, tid = _flatten_tool_call_dict(raw)
            if name != _KG_TOOL_NAME:
                continue
            if isinstance(args, dict):
                try:
                    preview = json.dumps(args, ensure_ascii=False)[:500]
                except Exception:
                    preview = str(args)[:500]
            else:
                preview = str(args)[:500]
            out.append(
                {
                    "tool_call_id": str(tid) if tid is not None else "",
                    "args_keys": list(args.keys()) if isinstance(args, dict) else [],
                    "args_preview": preview,
                }
            )
        return out
    return []


def _normalize_cypher_for_dedupe(cypher: str) -> str:
    s = (cypher or "").strip()
    if not s:
        return ""
    return re.sub(r"\s+", " ", s)


def _dedupe_key_from_norm(norm: str) -> str:
    return _CYPHER_DEDUPE_EMPTY_KEY if not (norm or "").strip() else norm


def _messages_tail_since_last_human(messages: Any) -> list[Any]:
    if not isinstance(messages, list):
        return []
    tail: list[Any] = []
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            break
        tail.append(m)
    tail.reverse()
    return tail


def _is_neo4j_tool_message(m: ToolMessage) -> bool:
    name = getattr(m, "name", None) or ""
    return name == _KG_TOOL_NAME or name == ""


def _neo4j_toolmessage_contents_since_last_human(messages: Any) -> list[str]:
    out: list[str] = []
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            break
        if isinstance(m, ToolMessage) and _is_neo4j_tool_message(m):
            body = m.content if isinstance(m.content, str) else str(m.content)
            out.append(body)
    out.reverse()
    return out


def _neo4j_invocations_since_last_human(messages: Any) -> int:
    return len(_neo4j_toolmessage_contents_since_last_human(messages))


def _is_neo4j_roundtrip_tool_content(content: str) -> bool:
    s = (content or "").strip()
    if not s:
        return False
    if s.startswith("【"):
        return False
    if s.startswith("查询失败:"):
        return True
    if "[已截断" in s[:400]:
        return True
    if s.startswith("[") or s.startswith("{"):
        return True
    return False


def _neo4j_roundtrips_since_last_human(messages: Any) -> int:
    return sum(
        1
        for c in _neo4j_toolmessage_contents_since_last_human(messages)
        if _is_neo4j_roundtrip_tool_content(c)
    )


def _neo4j_history_since_last_human(
    messages: Any,
) -> tuple[list[tuple[str, str]], deque[str]]:
    done: list[tuple[str, str]] = []
    pending: deque[str] = deque()
    for m in _messages_tail_since_last_human(messages):
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            for tc in m.tool_calls or []:
                raw = _coerce_tool_call_to_dict(tc)
                if not raw:
                    continue
                name, args, _tcid = _flatten_tool_call_dict(raw)
                if name != _KG_TOOL_NAME:
                    continue
                cq = _normalize_cypher_for_dedupe(_args_dict_to_cypher(args))
                pending.append(_dedupe_key_from_norm(cq))
        elif isinstance(m, ToolMessage) and _is_neo4j_tool_message(m):
            body = m.content if isinstance(m.content, str) else str(m.content)
            snippet = body[:800] + ("…" if len(body) > 800 else "")
            if pending:
                done.append((pending.popleft(), snippet))
            else:
                done.append((_CYPHER_DEDUPE_EMPTY_KEY, snippet))
    return done, pending


def _preflight_class_returns_since_last_human(messages: Any) -> int:
    n = 0
    for c in _neo4j_toolmessage_contents_since_last_human(messages):
        s = (c or "").strip()
        if s.startswith("【参数错误】") or s.startswith("【语法预检】") or s.startswith(
            "【安全拒绝】"
        ):
            n += 1
    return n


def _recent_kg_tool_summaries(messages: Any, max_n: int = 6) -> list[dict[str, Any]]:
    contents = _neo4j_toolmessage_contents_since_last_human(messages)
    if not contents:
        return []
    take = contents[-max_n:]
    out: list[dict[str, Any]] = []
    base = len(contents) - len(take)
    for i, c in enumerate(take):
        head = c[:180] + ("…" if len(c) > 180 else "")
        kind = "other"
        cs = (c or "").strip()
        if cs.startswith("【系统限制】"):
            kind = "system_cap"
        elif cs.startswith("【重复查询】"):
            kind = "duplicate"
        elif cs.startswith("【参数错误】"):
            kind = "param"
        elif cs.startswith("【语法预检】"):
            kind = "syntax"
        elif cs.startswith("【安全拒绝】"):
            kind = "security"
        elif cs.startswith("查询失败:"):
            kind = "neo4j_error"
        elif cs.startswith("[") or cs.startswith("{"):
            kind = "json"
        elif "[已截断" in cs[:400]:
            kind = "json_truncated"
        out.append({"i": base + i, "kind": kind, "head": head})
    return out


def _preflight_readonly_cypher(cypher: str) -> str | None:
    s = (cypher or "").strip()
    if not s:
        return (
            "【参数错误】Cypher 为空。请使用 JSON 对象参数，且键名必须为 cypher_query；"
            "不要传空对象或空字符串。"
            "若语句写在同条助手消息的 ```cypher 代码块或以 MATCH/CALL 开头的段落中，系统会尝试自动提取；"
            "若仍失败，请把完整只读 Cypher 填入工具参数 cypher_query。"
        )
    if len(s) < 8:
        return "【参数错误】Cypher 过短，请提交有效、完整的只读查询，勿重复提交无效内容。"
    if _FORBIDDEN_WRITE_RE.search(s):
        return (
            "【安全拒绝】仅允许只读查询：检测到写操作关键字，请改写为 MATCH/RETURN 等只读子句，"
            "勿反复提交同类违规语句。"
        )
    if not _READ_START_RE.search(s):
        return (
            "【语法预检】语句缺少 MATCH / OPTIONAL MATCH / CALL / WITH / UNWIND / RETURN 等可读入口，"
            "请确认是否为完整 Cypher，勿重复提交同类无效内容。"
        )
    parts = [p.strip() for p in s.split(";")]
    if len(parts) > 1 and any(len(p) > 0 for p in parts[1:]):
        return (
            "【语法预检】一次仅允许一条 Cypher：检测到分号后的额外语句；请拆成多次查询或合并为单条。"
        )
    return None


def _ai_message_plain_text(m: AIMessage) -> str:
    c = m.content
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts: list[str] = []
        for block in c:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "\n".join(parts)
    return str(c or "")


def _find_ai_for_neo4j_invocation(messages: Any, tool_call_id: str) -> AIMessage | None:
    if not isinstance(messages, list):
        return None
    tid = str(tool_call_id or "").strip()
    if tid:
        for m in reversed(messages):
            if not isinstance(m, AIMessage) or not getattr(m, "tool_calls", None):
                continue
            for tc in m.tool_calls or []:
                raw = _coerce_tool_call_to_dict(tc)
                if not raw:
                    continue
                name, _args, tcid = _flatten_tool_call_dict(raw)
                if name != _KG_TOOL_NAME:
                    continue
                if str(tcid or "").strip() == tid:
                    return m
    for m in reversed(messages):
        if not isinstance(m, AIMessage) or not getattr(m, "tool_calls", None):
            continue
        for tc in m.tool_calls or []:
            raw = _coerce_tool_call_to_dict(tc)
            if not raw:
                continue
            name, _args, _tcid = _flatten_tool_call_dict(raw)
            if name == _KG_TOOL_NAME:
                return m
    return None


def _extract_cypher_from_assistant_text(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    m = re.search(r"```(?:cypher)?\s*\r?\n(.*?)```", s, re.IGNORECASE | re.DOTALL)
    if m:
        inner = (m.group(1) or "").strip()
        if inner and _preflight_readonly_cypher(inner) is None:
            return inner
    m2 = re.search(r"(?is)((?:OPTIONAL\s+)?MATCH\b[\s\S]+)", s)
    if m2:
        chunk = m2.group(1).strip()
    else:
        m3 = re.search(r"(?is)(\bCALL\b[\s\S]+)", s)
        if not m3:
            return ""
        chunk = m3.group(1).strip()
    chunk = re.split(r"\n\s*\n", chunk, maxsplit=1)[0]
    chunk = chunk.split("```")[0].strip()
    if len(chunk) >= 8 and _preflight_readonly_cypher(chunk) is None:
        return chunk
    return ""


def _recover_cypher_from_ai_message_content(
    messages: Any, tool_call_id: str
) -> tuple[str, str]:
    ai = _find_ai_for_neo4j_invocation(messages, tool_call_id)
    if ai is None:
        return "", ""
    raw = _extract_cypher_from_assistant_text(_ai_message_plain_text(ai))
    if raw:
        return raw, "matched_ai_message_text"
    return "", ""


class _Neo4jQueryArgs(BaseModel):
    """工具参数 schema：cypher_query 必填，减少模型传 {}。"""

    cypher_query: str = Field(
        ...,
        description=(
            "必填，单条完整只读 Cypher。岗位标签为 JobPosting，职位名属性多为 name。"
            "示例：MATCH (jp:JobPosting)-[:REQUIRES_SKILL]->(s:Skill) WHERE toLower(s.name) CONTAINS "
            "'python' RETURN jp.name AS job_title LIMIT 20"
        ),
        min_length=1,
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_input(cls, data: Any) -> dict[str, Any]:
        if data is None:
            return {}
        if isinstance(data, str):
            s = data.strip()
            if s.startswith("{") and s.endswith("}"):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, dict):
                        return cls._normalize_input(parsed)
                except json.JSONDecodeError:
                    pass
            return {"cypher_query": s}
        if not isinstance(data, dict):
            return {"cypher_query": str(data).strip()}

        d = dict(data)
        raw_args = d.get("arguments")
        if isinstance(raw_args, str) and raw_args.strip():
            try:
                inner = json.loads(raw_args)
                if isinstance(inner, dict):
                    d.update(inner)
            except json.JSONDecodeError:
                pass

        cq = (
            d.get("cypher_query")
            or d.get("query")
            or d.get("cypher")
            or d.get("cypherQuery")
            or d.get("cypher_statement")
            or d.get("statement")
        )
        if isinstance(cq, str):
            cq = cq.strip()
        else:
            cq = ""

        if not cq:
            str_vals = [
                v.strip()
                for v in d.values()
                if isinstance(v, str) and v.strip() and not v.strip().startswith("{")
            ]
            for v in str_vals:
                upper = v.upper()
                if "MATCH" in upper or "RETURN" in upper or "CALL" in upper:
                    cq = v
                    break
            if not cq and len(str_vals) == 1:
                cq = str_vals[0]

        return {"cypher_query": cq if isinstance(cq, str) else str(cq or "").strip()}


def _duplicate_response(norm: str, done: list[tuple[str, str]]) -> str | None:
    key = _dedupe_key_from_norm(norm)
    prev_snippets = [sn for (n, sn) in done if n == key]
    if not prev_snippets:
        return None
    last = prev_snippets[-1]
    same_hint = (
        "空查询或无效绑定"
        if key == _CYPHER_DEDUPE_EMPTY_KEY
        else "相同 Cypher（空白折叠后一致）"
    )
    return (
        f"【重复查询】本回合已对{same_hint}处理过图谱工具请求，系统不会再次访问 Neo4j。"
        "你必须**禁止**再调用本工具，请直接依据上一条同键工具返回整理中文终局答案。"
        "若用户要查新数据，应请用户**再发一条新的用户消息**以便改写或新 Cypher。"
        f"\n--- 上次返回摘要（前 800 字）---\n{last}"
    )


@tool(args_schema=_Neo4jQueryArgs, infer_schema=False, parse_docstring=False)
def query_recruitment_knowledge_graph(
    cypher_query: str,
    state: Annotated[dict, InjectedState()],
    tool_call_id: Annotated[str, InjectedToolCallId()],
) -> str:
    """招聘知识图谱只读查询（Neo4j）。参数键名须为 cypher_query。"""
    try:
        parsed = _Neo4jQueryArgs.model_validate({"cypher_query": cypher_query})
        cypher_query = parsed.cypher_query.strip()
    except Exception:
        cypher_query = (cypher_query or "").strip()

    msgs = state.get("messages") or []
    if not cypher_query:
        recovered, how_id = _recover_cypher_from_ai_tool_calls(msgs, tool_call_id)
        how_fb = ""
        how_txt = ""
        if not recovered:
            recovered, how_fb = _recover_cypher_fallback_last_ai(msgs)
        if not recovered:
            recovered, how_txt = _recover_cypher_from_ai_message_content(
                msgs, tool_call_id
            )
        if recovered:
            cypher_query = recovered
            _log_kg_event(
                "cypher_recovered",
                recovery_source=how_id or how_fb or how_txt,
                tool_call_id_preview=(tool_call_id or "")[:48],
                cypher_len=len(cypher_query),
            )
        else:
            _log_kg_event(
                "cypher_bind_empty",
                tool_call_id_preview=(tool_call_id or "")[:48],
                recover_by_id_reason=how_id or None,
                recover_fallback_reason=how_fb or None,
                recover_text_reason=how_txt or None,
                neo4j_tool_calls_diag=_diag_neo4j_tool_calls_in_messages(msgs),
            )

    cypher_query = _trim_tool_call_json_leak(cypher_query)

    cap = settings.QA_MAX_KG_TOOL_INVOCATIONS_PER_TURN
    hard = settings.QA_MAX_KG_TOOL_MESSAGES_HARD_CAP
    used_total = _neo4j_invocations_since_last_human(msgs)
    roundtrips = _neo4j_roundtrips_since_last_human(msgs)
    norm = _normalize_cypher_for_dedupe(cypher_query)
    preview = norm[:80]
    tail_n = len(_messages_tail_since_last_human(msgs))
    recent = _recent_kg_tool_summaries(msgs)

    _log_kg_event(
        "invoke_begin",
        cypher_preview=preview,
        cypher_len=len(cypher_query or ""),
        norm_fingerprint=_norm_fingerprint(norm),
        used_total=used_total,
        roundtrips=roundtrips,
        cap_rounds=cap,
        hard_cap=hard,
        tail_message_count=tail_n,
        recent_tools=recent,
    )
    _log_kg_verbose_cypher(cypher_query)

    if used_total >= hard:
        _log_kg_event(
            "hard_cap",
            cypher_preview=preview,
            cypher_len=len(cypher_query or ""),
            norm_fingerprint=_norm_fingerprint(norm),
            used_total=used_total,
            roundtrips=roundtrips,
            cap_rounds=cap,
            hard_cap=hard,
            recent_tools=recent,
        )
        return (
            f"【系统限制】本回合图谱工具返回次数已达硬上限（{hard} 次）。"
            "请在本条用户问题对应的多轮对话中**禁止**再调用本工具；请根据已有 ToolMessage 整理终局回答，可说明信息不足并辅以常识推断。"
        )

    done, _pending = _neo4j_history_since_last_human(msgs)
    dup = _duplicate_response(norm, done)
    if dup is not None:
        _log_kg_event(
            "duplicate",
            cypher_preview=preview,
            norm_fingerprint=_norm_fingerprint(norm),
            used_total=used_total,
            roundtrips=roundtrips,
            recent_tools=recent,
        )
        return dup

    preflight_errs = _preflight_class_returns_since_last_human(msgs)
    pre_cap = settings.QA_MAX_KG_TOOL_PREFLIGHT_ERRORS_PER_TURN
    if preflight_errs >= pre_cap:
        _log_kg_event(
            "preflight_cap",
            cypher_preview=preview,
            norm_fingerprint=_norm_fingerprint(norm),
            used_total=used_total,
            roundtrips=roundtrips,
            preflight_errors=preflight_errs,
            preflight_cap=pre_cap,
            recent_tools=recent,
        )
        return (
            f"【系统限制】本回合图谱工具参数/语法/安全预检类返回已累计 {pre_cap} 次，"
            "系统不再接受新的图谱查询。请在本条用户问题对应的多轮对话中**禁止**再调用本工具；"
            "请根据已有 ToolMessage 整理终局回答，可说明信息不足并辅以常识推断。"
        )

    bad = _preflight_readonly_cypher(cypher_query)
    if bad is not None:
        _log_kg_event(
            "preflight",
            cypher_preview=preview,
            preflight_detail=(bad or "")[:400],
            used_total=used_total,
            roundtrips=roundtrips,
            recent_tools=recent,
        )
        return bad

    if roundtrips >= cap:
        _log_kg_event(
            "neo4j_round_cap",
            cypher_preview=preview,
            norm_fingerprint=_norm_fingerprint(norm),
            used_total=used_total,
            roundtrips=roundtrips,
            cap_rounds=cap,
            hard_cap=hard,
            recent_tools=recent,
        )
        return (
            f"【系统限制】本回合 Neo4j 读库次数已达上限（{cap} 次）；"
            "预检/重复类返回不计入该上限。请**禁止**再调用本工具；若已有返回的图谱 JSON 或报错，请直接整理中文终局答案，勿再试。"
        )

    svc = Neo4jReadOnlyService()
    t0 = time.perf_counter()
    try:
        records = svc.execute_readonly_query(cypher_query, None)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        text = json.dumps(records, ensure_ascii=False, default=str)
        rec_count = len(records) if isinstance(records, list) else -1
        truncated = len(text) > MAX_TOOL_RESULT_CHARS
        _log_kg_event(
            "neo4j_ok",
            cypher_preview=preview,
            norm_fingerprint=_norm_fingerprint(norm),
            used_total=used_total,
            roundtrips=roundtrips,
            duration_ms=elapsed_ms,
            records_count=rec_count,
            result_chars=len(text),
            result_truncated=truncated,
            recent_tools=recent,
        )
        if truncated:
            return (
                text[:MAX_TOOL_RESULT_CHARS]
                + f"\n...[已截断，共 {len(text)} 字符]"
            )
        return text
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        _log_kg_event(
            "neo4j_error",
            cypher_preview=preview,
            norm_fingerprint=_norm_fingerprint(norm),
            used_total=used_total,
            roundtrips=roundtrips,
            duration_ms=elapsed_ms,
            exc_type=type(e).__name__,
            exc_msg=str(e)[:800],
            recent_tools=recent,
        )
        if settings.QA_KG_TOOL_VERBOSE_LOG:
            logger.exception(
                "kg_tool neo4j_exception thread_id=%s", _runtime_thread_id()
            )
        return (
            f"查询失败: {e}\n"
            "请根据报错修改 Cypher（标签/关系类型与图谱不一致、缺少 LIMIT 导致过大结果等）。"
            "若已连续两次相同失败，勿重复提交。"
        )
    finally:
        svc.close()
