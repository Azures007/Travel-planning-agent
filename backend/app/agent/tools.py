"""Agent 工具注册表：把 Python 函数暴露给 LLM 调用。

P1 使用 Mock 实现；P2 切换到真实 API 时只需替换函数内部实现，
工具名/参数/返回值保持兼容即可。
"""

from app.schemas import ItineraryPlan
from app.tools.mock_tools import calc_transit, get_weather, search_poi

# 工具定义（OpenAI 兼容格式，DashScope 支持）
TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "search_poi",
            "description": "搜索某个目的地内的景点/地点，返回地点名称、分类、评分、开放时间和门票价格。规划行程前应先调用它了解当地有哪些可去的地方。",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string", "description": "目的地城市名，如 大理"},
                    "keyword": {"type": "string", "description": "可选，地点关键词，如 古城/雪山"},
                },
                "required": ["destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询目的地未来几天的天气情况，返回季节和逐日天气预报，用于规划出行和穿衣建议。",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string", "description": "目的地城市名"},
                    "days": {"type": "integer", "description": "需要几天预报，通常等于行程天数"},
                },
                "required": ["destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc_transit",
            "description": "估算两个地点之间的交通耗时，用于校验行程衔接是否合理。",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "出发地地点名"},
                    "destination": {"type": "string", "description": "到达地地点名"},
                    "mode": {"type": "string", "enum": ["driving", "transit", "walking"], "description": "交通方式"},
                },
                "required": ["origin", "destination"],
            },
        },
    },
]

# 工具名 -> 处理函数
_TOOL_HANDLERS = {
    "search_poi": search_poi,
    "get_weather": get_weather,
    "calc_transit": calc_transit,
}

# 供 agent 逻辑引用的工具描述（含 ItineraryPlan schema 信息）
AGENT_TOOL_NAMES = [t["function"]["name"] for t in TOOL_DEFS]


def call_tool(name: str, arguments: dict):
    """执行工具调用，返回结果 dict 或错误信息。"""
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        return {"error": f"未知工具: {name}"}
    try:
        result = handler(**arguments)
    except TypeError as e:
        return {"error": f"工具参数错误: {e}"}
    return result


def itinerary_tool_def() -> dict:
    """输出工具定义（描述 ItineraryPlan schema，让模型直接产出结构化行程）。"""
    schema = ItineraryPlan.model_json_schema()
    return {
        "type": "function",
        "function": {
            "name": "output_itinerary",
            "description": "在收集齐需求要素并查询完地点/天气/交通后，调用本工具输出最终的完整行程计划。调用时参数必须严格符合 schema。",
            "parameters": schema,
        },
    }
