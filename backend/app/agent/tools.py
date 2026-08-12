"""Agent 工具注册表：把工具暴露给 LLM 调用。

P1 使用 Mock 实现；P2 通过 registry 按 Key 选择真实 API 并自动降级。
工具名/参数/返回值保持兼容。
"""

from app.schemas import ItineraryPlan

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
