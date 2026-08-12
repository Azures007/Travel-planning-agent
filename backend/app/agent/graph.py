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


class TravelState(TypedDict, total=False):
    messages: list[dict]            # OpenAI 格式历史（含 tool_calls/tool 消息），无 reducer（节点返回全量）
    requirements: dict | None       # TripRequirements 草稿
    itinerary: dict | None          # 当前行程草稿（ItineraryPlan.model_dump()）
    validation: dict | None         # {"ok", "issues": [{rule,level,message}], "errors"}
    retries: int                    # 校验失败重试计数
    pending_question: str | None    # 待问的问题（collect 决定，ask_user 消费）


def route_after_collect(state: TravelState) -> str:
    """collect 后路由：工具调用自环 / 追问 / 生成。

    优先级：
    1. 本轮执行了数据工具 → 自环继续收集
    2. 需求已齐（destination + days + 预算）→ 生成
    3. 模型明确在追问（问句且需求不齐）→ ask_user
    """
    messages = state.get("messages") or []
    if messages and messages[-1].get("role") == "tool":
        return "collect"  # 本轮执行了数据工具，继续收集

    if state.get("pending_question"):
        return "ask_user"

    req = state.get("requirements") or {}
    # 需求核心要素齐备：目的地 + 天数 + 预算（预算缺失时也允许，模型可生成后让用户调）
    if req.get("destination") and req.get("days"):
        return "generate"

    # 需求不齐：若模型在追问，进 ask_user；否则兜底追问
    if messages and messages[-1].get("role") == "assistant":
        last_text = messages[-1].get("content", "") or ""
        if any(mark in last_text for mark in ("？", "?", "吗？", "呢？")):
            state["pending_question"] = last_text[-300:]  # 截断，避免过长
            return "ask_user"

    # 需求不足且模型未追问 → 兜底追问
    state["pending_question"] = (
        state.get("pending_question")
        or "请问你想去哪里旅行？打算玩几天？大概预算多少？"
    )
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
