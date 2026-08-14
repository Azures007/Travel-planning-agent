"""LLM 封装：AsyncOpenAI 直连 DashScope（OpenAI 兼容接口）。

在 LangGraph 节点内调用，通过 get_stream_writer 把文本增量透传为
custom 事件（runner 消费后转发为 SSE 的 agent_message / tool_result）。

方案3：发送给 API 前先做上下文压缩（旧对话 → 摘要），State/DB 不受影响。
"""

import json
import logging
from dataclasses import dataclass, field

from langgraph.config import get_stream_writer
from openai import AsyncOpenAI

from app.agent.prompts import SYSTEM_SUMMARY
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)  # OpenAI 格式 [{id,type,function}]


class LLM:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        # 摘要缓存：key=被压缩消息的指纹，value=摘要文本，避免重复压缩
        self._summary_cache: dict[str, str] = {}

    # ---- 上下文压缩（方案3）----

    @staticmethod
    def _estimate_tokens(messages: list[dict]) -> int:
        """粗略估算 token 数（无 tokenizer，用字符数近似）。"""
        total = 0
        for m in messages:
            content = m.get("content") or ""
            # 中文约 1 字 ≈ 1 token，英文约 4 字符 ≈ 1 token，折中取 0.7
            total += int(len(content) * 0.7)
            if m.get("tool_calls"):
                total += 50  # 工具调用结构开销
        return total

    @staticmethod
    def _fingerprint(messages: list[dict]) -> str:
        """计算消息列表指纹（用于摘要缓存）。"""
        parts = []
        for m in messages:
            c = (m.get("content") or "")[:200]
            parts.append(f"{m.get('role')}:{len(c)}:{c}")
        return "|".join(parts)[-2000:]

    async def _summarize(self, old_messages: list[dict]) -> str:
        """用一次非流式调用把旧对话压缩成摘要。失败返回空串（调用方兜底不压缩）。"""
        fp = self._fingerprint(old_messages)
        if fp in self._summary_cache:
            return self._summary_cache[fp]

        # 把旧消息转成可读文本
        lines = []
        for m in old_messages:
            role = m.get("role", "")
            content = m.get("content") or ""
            if m.get("tool_calls"):
                lines.append(f"[assistant 调用了工具]")
            elif role == "tool":
                lines.append(f"[工具结果] {content[:200]}")
            else:
                lines.append(f"{role}: {content}")
        dialog_text = "\n".join(lines)

        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_SUMMARY},
                    {"role": "user", "content": f"对话历史：\n{dialog_text[:8000]}"},
                ],
                max_tokens=500,
                stream=False,
            )
            summary = (resp.choices[0].message.content or "").strip()
            if summary:
                self._summary_cache[fp] = summary
            return summary
        except Exception as e:
            logger.warning("上下文摘要生成失败: %s（本次不压缩）", e)
            return ""

    async def _compress_if_needed(self, messages: list[dict]) -> list[dict]:
        """超过阈值时，把除最近 N 条外的旧消息压缩成摘要，插在开头。"""
        threshold = settings.context_compress_threshold
        keep_recent = settings.context_keep_recent

        if self._estimate_tokens(messages) <= threshold:
            return messages

        # 保留最近的 keep_recent 条，压缩更早的
        keep = messages[-keep_recent:]
        old = messages[:-keep_recent]
        if len(old) < 2:
            return messages  # 旧消息太少不值得压缩

        summary = await self._summarize(old)
        if not summary:
            return messages  # 摘要失败，保持原样（宁可多用 token 也不丢信息）

        logger.info("上下文压缩: %d 条旧消息 → 摘要 (节省约 %d token)",
                    len(old), self._estimate_tokens(old))
        # 摘要消息插在最前（保留 system 提示在前面）
        summary_msg = {"role": "system", "content": f"[早前对话摘要]\n{summary}"}
        return [summary_msg] + keep

    # ---- 主调用 ----

    async def turn(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        system: str | None = None,
        emit_as: str = "agent_message",
    ) -> LLMResult:
        """执行一轮 LLM 调用（流式），返回完整回复。

        文本增量通过 get_stream_writer 透传为 custom 事件；
        工具调用按 index 分槽拼装，流结束后返回完整结构。
        发送前做上下文压缩（超阈值时）。

        emit_as: 文本增量事件类型。collect 阶段传 "process_message"
        （前端折叠为进度状态条），generate 阶段保持默认 "agent_message"
        （作为正式回复气泡）。
        """
        writer = get_stream_writer()

        api_messages = messages
        if system:
            api_messages = [{"role": "system", "content": system}] + list(messages)

        # 方案3：上下文压缩（只在发给 API 前生效）
        api_messages = await self._compress_if_needed(api_messages)

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
                        "type": emit_as,
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
