"""LLM 工厂：与具体 Agent 解耦，配置来自 Settings / 环境变量。"""
from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langchain_openai import ChatOpenAI

from app.core.config import settings


class ChatOpenAIEmptyStreamFallback(ChatOpenAI):
    """部分 OpenAI 兼容网关对 stream=true 返回空 body/SSE 时，改走非流式 completion。"""

    def _stream(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        n = 0
        for chunk in super()._stream(
            messages, stop=stop, run_manager=run_manager, **kwargs
        ):
            n += 1
            yield chunk
        if n == 0:
            res = self._generate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )
            yield self._chat_result_to_chunk(res)

    async def _astream(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        n = 0
        async for chunk in super()._astream(
            messages, stop=stop, run_manager=run_manager, **kwargs
        ):
            n += 1
            yield chunk
        if n == 0:
            res = await self._agenerate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )
            yield self._chat_result_to_chunk(res)

    @staticmethod
    def _chat_result_to_chunk(result: Any) -> ChatGenerationChunk:
        gen = result.generations[0]
        m = gen.message
        return ChatGenerationChunk(
            message=AIMessageChunk(
                content=m.content,
                additional_kwargs=dict(m.additional_kwargs or {}),
                response_metadata=dict(m.response_metadata or {}),
                tool_calls=list(m.tool_calls) if m.tool_calls else [],
                invalid_tool_calls=list(m.invalid_tool_calls)
                if m.invalid_tool_calls
                else [],
                usage_metadata=m.usage_metadata,
                id=m.id,
                chunk_position="last",
            ),
            generation_info=gen.generation_info,
        )


def build_chat_model(
    *,
    model: str | None = None,
    temperature: float | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    max_tokens: int | None = None,
) -> ChatOpenAIEmptyStreamFallback:
    """构造 Chat 模型；未传参数时使用应用 Settings。"""
    mt = (
        max_tokens
        if max_tokens is not None
        else settings.llm_effective_max_output_tokens()
    )
    return ChatOpenAIEmptyStreamFallback(
        model=model or settings.LLM_MODEL,
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
        api_key=api_key if api_key is not None else settings.LLM_API_KEY,
        base_url=base_url or settings.OPENAI_BASE_URL,
        max_tokens=mt,
        output_version="v0",
        model_kwargs={"parallel_tool_calls": False},
    )


_default_llm: ChatOpenAIEmptyStreamFallback | None = None


def get_default_chat_model() -> ChatOpenAIEmptyStreamFallback:
    """进程内单例，供非 Agent 代码（如根目录 config兼容入口）使用。"""
    global _default_llm
    if _default_llm is None:
        _default_llm = build_chat_model()
    return _default_llm
