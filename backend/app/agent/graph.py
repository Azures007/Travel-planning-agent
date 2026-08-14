"""LangGraph 图定义：TravelState + build_graph() + 条件路由。

结构：
  START → collect →(数据工具自环)────────────────┐
            ├(pending_question)→ ask_user ────────┤(interrupt, 恢复后回 collect)
            └(需求齐)→ generate → validate ─(ok)→ END
                               ├(fail, retries<2)→ generate
                               └(fail, retries>=2)→ END
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import ask_user, collect, generate, validate

MAX_VALIDATE_RETRIES = 2

# 需求收集的必问字段（缺任一 → 追问）
REQUIRED_FIELDS = ["destination", "days", "budget", "travelers", "pace", "preferences", "departure_date"]

# 字段对应的提问文案
FIELD_QUESTIONS = {
    "destination": "想去哪个城市或目的地？",
    "days": "打算玩几天？",
    "budget": "大概预算是多少？",
    "travelers": "几个人出行？",
    "pace": "节奏偏好是轻松还是紧凑？",
    "preferences": "有什么兴趣偏好（美食/自然/人文/摄影等）？",
    "departure_date": "打算什么时候出发？",
}


def missing_fields(req: dict) -> list[str]:
    """返回当前缺失的必问字段列表。"""
    return [f for f in REQUIRED_FIELDS if not req.get(f)]


class TravelState(TypedDict, total=False):
    messages: list[dict]            # OpenAI 格式历史（含 tool_calls/tool 消息），无 reducer（节点返回全量）
    requirements: dict | None       # TripRequirements 草稿
    itinerary: dict | None          # 当前行程草稿（ItineraryPlan.model_dump()）
    validation: dict | None         # {"ok", "issues": [{rule,level,message}], "errors"}
    retries: int                    # 校验失败重试计数
    pending_question: str | None    # 待问的问题（collect 决定，ask_user 消费）


def route_after_collect(state: TravelState) -> str:
    """collect 后路由：工具调用自环 / 追问 / 生成。

    注意：路由函数是只读的，不能修改 state。pending_question 由 collect 节点
    在返回时计算并更新（缺字段时设置），这里只做判断。
    """
    messages = state.get("messages") or []
    if messages and messages[-1].get("role") == "tool":
        return "collect"  # 本轮执行了数据工具，继续收集

    if state.get("pending_question"):
        return "ask_user"  # collect 已算出缺字段 → 追问

    req = state.get("requirements") or {}
    if not missing_fields(req):
        return "generate"  # 所有必问字段齐备

    # 兜底：理论上前一步已设置 pending_question，这里防御性兜底
    return "ask_user"


def route_after_validate(state: TravelState) -> str:
    """validate 后路由：通过结束 / 失败重生成 / 耗尽带警告结束。"""
    v = state.get("validation") or {}
    if v.get("ok"):
        return "end"
    if (state.get("retries") or 0) < MAX_VALIDATE_RETRIES:
        return "generate"
    return "end"


def build_graph(checkpointer):
    g = StateGraph(TravelState)

    g.add_node("collect", collect)
    g.add_node("ask_user", ask_user)
    g.add_node("generate", generate)
    g.add_node("validate", validate)

    g.add_edge(START, "collect")
    g.add_conditional_edges(
        "collect",
        route_after_collect,
        {"collect": "collect", "ask_user": "ask_user", "generate": "generate"},
    )
    g.add_edge("ask_user", "collect")
    g.add_edge("generate", "validate")
    g.add_conditional_edges(
        "validate",
        route_after_validate,
        {"generate": "generate", "end": END},
    )

    return g.compile(checkpointer=checkpointer)
