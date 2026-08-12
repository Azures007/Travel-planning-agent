"""LLM 封装：AsyncOpenAI 直连 DashScope（OpenAI 兼容接口）。

在 LangGraph 节点内调用，通过 get_stream_writer 把文本增量透传为
custom 事件（runner 消费后转发为 SSE 的 agent_message / tool_result）。
"""

import json
from dataclasses import dataclass, field

from langgraph.config import get_stream_writer
from openai import AsyncOpenAI


@dataclass
class LLMResult:
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)  # OpenAI 格式 [{id,type,function}]


class LLM:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    async def turn(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        system: str | None = None,
    ) -> LLMResult:
        """执行一轮 LLM 调用（流式），返回完整回复。

        文本增量通过 get_stream_writer 透传为 custom 事件；
        工具调用按 index 分槽拼装，流结束后返回完整结构。
        """
        writer = get_stream_writer()

        api_messages = messages
        if system:
            api_messages = [{"role": "system", "content": system}] + list(messages)

        kwargs: dict = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": 4096,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        stream = await self.client.chat.completions.create(**kwargs)

        content_parts: list[str] = []
        tool_calls: dict[int, dict] = {}

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                content_parts.append(delta.content)
                writer(
                    {
                        "type": "agent_message",
                        "data": {"text": delta.content},
                    }
                )
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    slot = tool_calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["arguments"] += tc.function.arguments

        result = LLMResult(content="".join(content_parts))
        for idx in sorted(tool_calls):
            tc = tool_calls[idx]
            result.tool_calls.append(
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
            )
        return result


def parse_tool_arguments(tool_call: dict) -> dict:
    """解析工具调用参数的 JSON 字符串。失败返回 {}。"""
    args_str = (tool_call.get("function") or {}).get("arguments") or ""
    try:
        return json.loads(args_str) if args_str else {}
    except json.JSONDecodeError:
        return {}
