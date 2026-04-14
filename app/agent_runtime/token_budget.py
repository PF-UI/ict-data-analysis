"""对话 token 粗估与 llm_input_messages 截断（避免超过上下文窗口）。"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


def estimate_text_tokens(text: str, divisor: float) -> int:
    if not text:
        return 0
    n = len(text.encode("utf-8"))
    d = max(divisor, 0.5)
    return max(1, int(n / d))


def message_text_content(msg: BaseMessage) -> str:
    c = getattr(msg, "content", None)
    if c is None:
        return ""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts: list[str] = []
        for block in c:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(c)


def estimate_message_tokens(msg: BaseMessage, divisor: float) -> int:
    t = estimate_text_tokens(message_text_content(msg), divisor)
    extra = 0
    if isinstance(msg, AIMessage) and msg.tool_calls:
        try:
            raw = json.dumps(msg.tool_calls, ensure_ascii=False)
            extra = estimate_text_tokens(raw, divisor)
        except (TypeError, ValueError):
            extra = 256
    if isinstance(msg, ToolMessage):
        extra += estimate_text_tokens(str(getattr(msg, "name", "") or ""), divisor)
    return t + extra


def estimate_user_question_tokens(text: str, divisor: float) -> int:
    return estimate_text_tokens(text.strip(), divisor)


def truncate_llm_input_messages(
    cleaned: list[BaseMessage],
    max_prompt_tokens: int,
    divisor: float,
) -> list[BaseMessage]:
    """在已 sanitize 的消息序列上，从头部丢弃直到粗估 token 低于上限，再 sanitize 一次。"""
    from app.agent_runtime.hooks.dashscope_tool_calls import sanitize_messages_for_tool_chat

    msgs = list(cleaned)
    if max_prompt_tokens <= 0:
        return msgs

    def total() -> int:
        return sum(estimate_message_tokens(m, divisor) for m in msgs)

    while msgs and total() > max_prompt_tokens:
        msgs.pop(0)
    return sanitize_messages_for_tool_chat(msgs)
