"""Agent 核心：基于 DashScope（OpenAI 兼容接口）的工具调用循环。

流程：收集需求 -> 调工具（查 POI/天气/交通）-> output_itinerary 产出结构化行程。
返回给 API 层的是一个事件生成器，支持 SSE 流式。

P1 目标：跑通最小闭环，逻辑尽量简单清晰，不引入 LangGraph。
"""

import json
from typing import AsyncIterator

from openai import AsyncOpenAI

from app.agent.tools import TOOL_DEFS, call_tool, itinerary_tool_def
from app.config import settings
from app.schemas import ItineraryPlan

SYSTEM_PROMPT = """你是一名专业的中文旅游规划助手，帮助用户生成个性化的行程计划。

工作流程：
1. 收集需求：目的地、天数、预算、出行人员、节奏偏好、兴趣等。信息不足时主动追问，一次只追问最关键的 1-2 个问题，不要长篇大论。
2. 查询信息：调用 search_poi 查询目的地的景点，调用 get_weather 查询天气，需要时用 calc_transit 估算交通耗时。
3. 生成行程：需求收集齐、信息查询完毕后，调用 output_itinerary 输出结构化的完整行程计划。

生成行程的要求：
- 每天安排 3-5 个活动，时间合理，不要安排得太满；预留吃饭、休息和交通时间。
- 同一目的地内的地点之间用步行或短途交通衔接，符合实际地理顺序。
- 行程要符合用户的节奏偏好（轻松/适中/紧凑）、出行人员（老人小孩要放慢节奏）和预算。
- 预算估算要合理，包含门票、交通、餐饮等；但不要把住宿和往返大交通算入行程内（那是总额外的）。
- 所有输出使用中文。

注意：用户还没有明确说要生成行程时，先确认需求；用户要求修改时，基于已有行程调整。

强制要求：只要用户已经给出了目的地和天数，无论首次生成还是修改，最终都必须调用 output_itinerary 输出完整行程。修改时同样要重新输出修改后的完整行程，不要只回复文字。"""


class AgentEvent:
    """SSE 事件类型"""

    def __init__(self, kind: str, data: dict):
        self.kind = kind
        self.data = data


class AgentRunner:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    async def run(self, messages: list[dict]) -> AsyncIterator[AgentEvent]:
        """执行 agent 循环。messages 为完整对话历史（含当前用户消息）。

        事件流：
          - agent_message: 模型自然语言回复（片段）
          - tool_call: 模型请求调用工具（含工具名和参数）
          - tool_result: 工具执行结果
          - itinerary: 最终结构化行程
        """
        tools = TOOL_DEFS + [itinerary_tool_def()]
        max_rounds = 8  # 工具调用循环上限，防止死循环

        # 构造本轮请求：系统提示 + 历史
        api_messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        api_messages.extend(messages)

        for _round in range(max_rounds):
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                tools=tools,
                max_tokens=4096,
                stream=True,
            )

            # 收集完整回复（tool_use 需要在流结束后处理）
            content_parts: list[str] = []
            tool_calls: dict[int, dict] = {}

            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    content_parts.append(delta.content)
                    # 流式透传给前端
                    yield AgentEvent(
                        "agent_message",
                        {"text": delta.content},
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

            # 处理工具调用
            if tool_calls:
                assistant_msg: dict = {"role": "assistant", "content": "".join(content_parts), "tool_calls": []}
                for idx in sorted(tool_calls):
                    tc = tool_calls[idx]
                    assistant_msg["tool_calls"].append(
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                    )

                api_messages.append(assistant_msg)

                for idx in sorted(tool_calls):
                    tc = tool_calls[idx]
                    name, arguments = tc["name"], tc["arguments"]
                    try:
                        args = json.loads(arguments) if arguments else {}
                    except json.JSONDecodeError:
                        args = {}

                    # 结构化行程输出：校验并返回
                    if name == "output_itinerary":
                        try:
                            plan = ItineraryPlan.model_validate(args)
                            yield AgentEvent("itinerary", {"plan": plan.model_dump()})
                            return
                        except Exception as e:
                            # schema 校验失败，把错误回传给模型让它修正
                            error_msg = f"输出不符合行程 schema，请修正后重新调用 output_itinerary。错误: {e}"
                            api_messages.append(
                                {"role": "tool", "tool_call_id": tc["id"], "content": error_msg}
                            )
                            yield AgentEvent("tool_result", {"name": name, "result": {"error": error_msg}})
                            continue

                    result = call_tool(name, args)
                    result_str = json.dumps(result, ensure_ascii=False)
                    api_messages.append(
                        {"role": "tool", "tool_call_id": tc["id"], "content": result_str}
                    )
                    yield AgentEvent("tool_result", {"name": name, "result": result})

                continue  # 有工具调用，进入下一轮循环

            # 没有工具调用：正常文本回复，结束
            text = "".join(content_parts)
            if not text.strip():
                yield AgentEvent("agent_message", {"text": "（抱歉，我没有理解你的意思，请再说一次。）"})
            return

        # 达到最大轮数（理论上不会到这里）
        yield AgentEvent(
            "agent_message",
            {"text": "处理请求的步骤太多，请简化需求后重试。"},
        )
