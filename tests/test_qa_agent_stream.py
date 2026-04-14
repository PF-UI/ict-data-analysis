"""Mock测试：stream_agent_answer 从 astream_events 提取文本片段。"""
import asyncio
import sys
import types
import unittest
from unittest.mock import patch

from langchain_core.messages.ai import AIMessageChunk


def _install_stub_config():
    stub = types.ModuleType("config")
    stub.llm = object()
    sys.modules["config"] = stub


class TestStreamAgentAnswer(unittest.TestCase):
    def test_yields_text_from_chat_model_stream(self):
        _install_stub_config()

        async def fake_astream_events(_state, config=None, version="v2"):
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": AIMessageChunk(content="你好")},
            }
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": AIMessageChunk(content="世界")},
            }
            yield {"event": "on_tool_start", "data": {}}

        mock_agent = type("G", (), {})()
        mock_agent.astream_events = fake_astream_events

        async def run():
            import importlib

            import app.agents.qa_agent as qa_agent

            importlib.reload(qa_agent)
            with patch(
                "app.agent_runtime.streaming.get_compiled_graph",
                return_value=mock_agent,
            ):
                parts = [
                    p
                    async for p in qa_agent.stream_agent_answer(
                        "测试问题", thread_id="test-thread"
                    )
                ]
            return parts

        parts = asyncio.run(run())
        self.assertEqual(parts, ["你好", "世界"])

    def test_qa_payloads_include_tool_events(self):
        _install_stub_config()

        async def fake_astream_events(_state, config=None, version="v2"):
            yield {
                "event": "on_tool_start",
                "name": "query_recruitment_knowledge_graph",
                "data": {"input": {"cypher_query": "MATCH (n) RETURN n LIMIT 1"}},
            }
            yield {
                "event": "on_tool_end",
                "name": "query_recruitment_knowledge_graph",
                "data": {"output": "[]"},
            }
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": AIMessageChunk(content="答")},
            }

        mock_agent = type("G", (), {})()
        mock_agent.astream_events = fake_astream_events

        async def run():
            import importlib

            import app.agent_runtime.streaming as streaming

            importlib.reload(streaming)
            with patch(
                "app.agent_runtime.streaming.get_compiled_graph",
                return_value=mock_agent,
            ):
                out = [
                    p
                    async for p in streaming.stream_agent_qa_payloads(
                        "测试问题", thread_id="test-thread"
                    )
                ]
            return out

        payloads = asyncio.run(run())
        self.assertEqual(
            [p.get("type") for p in payloads],
            ["tool_start", "tool_end", "chunk"],
        )
        self.assertEqual(payloads[-1].get("content"), "答")


if __name__ == "__main__":
    unittest.main()
