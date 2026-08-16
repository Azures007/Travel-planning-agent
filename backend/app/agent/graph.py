"""LangGraph 图定义：TravelState + build_graph() + 条件路由。

结构：
  START → collect →(数据工具自环)────────────────────────┐
            ├(pending_question)→ prepare_question → do_interrupt ────┤(interrupt, 恢复后回 collect)
            └(需求齐)→ generate → validate ─(ok)→ END
                               ├(fail, retries<2)→ generate
                               └(fail, retries>=2)→ END
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import collect, generate, validate, prepare_question, do_interrupt

MAX_VALIDATE_RETRIES = 2

# 需求收集的必问字段（缺任一 → 追问）
# 优化：只保留核心三项，其他字段使用智能默认值
REQUIRED_FIELDS = ["destination", "days", "budget"]

# 字段对应的提问文案
FIELD_QUESTIONS = {
    "destination": "想去哪个城市或目的地？",
    "days": "打算玩几天？",
    "budget": "大概预算是多少？",
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
    is_answering: bool              # 标记本轮用户是否在回答追问（ask_user 设置，collect 检查后清除）
    last_question_sent: str | None  # 最后发送的追问（ask_user 设置，用于避免 interrupt 恢复时重复发送）
    defaults_applied: bool          # 标记是否已应用默认值
    defaults_confirmed: bool        # 标记用户是否已确认默认值


def route_after_collect(state: TravelState) -> str:
    """collect 后路由：工具调用自环 / 追问 / 生成。

    注意：路由函数是只读的，不能修改 state。pending_question 由 collect 节点
    在返回时计算并更新（缺字段时设置），这里只做判断。
    """
    messages = state.get("messages") or []
    if messages and messages[-1].get("role") == "tool":
        return "collect"  # 本轮执行了数据工具，继续收集

    if state.get("pending_question"):
        return "prepare_question"  # collect 已算出缺字段 → 准备追问

    req = state.get("requirements") or {}
    if not missing_fields(req):
        return "generate"  # 所有必问字段齐备

    # 兜底：理论上前一步已设置 pending_question，这里防御性兜底
    return "prepare_question"


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
    g.add_node("prepare_question", prepare_question)
    g.add_node("do_interrupt", do_interrupt)
    g.add_node("generate", generate)
    g.add_node("validate", validate)

    g.add_edge(START, "collect")
    g.add_conditional_edges(
        "collect",
        route_after_collect,
        {"collect": "collect", "prepare_question": "prepare_question", "generate": "generate"},
    )
    g.add_edge("prepare_question", "do_interrupt")
    g.add_edge("do_interrupt", "collect")
    g.add_edge("generate", "validate")
    g.add_conditional_edges(
        "validate",
        route_after_validate,
        {"generate": "generate", "end": END},
    )

    return g.compile(checkpointer=checkpointer)
