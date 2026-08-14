"""LangGraph 节点：collect / ask_user / generate / validate。

注意：ask_user 是全图唯一 interrupt 所在节点。interrupt 恢复时节点会从顶部
重跑，因此 ask_user 在 interrupt 之前不能有任何副作用（不写 DB、不调 LLM）。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from app.agent.llm import LLM, parse_tool_arguments
from app.agent.prompts import SYSTEM_COLLECT, SYSTEM_GENERATION, VALIDATION_FEEDBACK
from app.agent.tools import TOOL_DEFS, itinerary_tool_def
from app.agent.validation import check_geography, try_auto_fix, validate_itinerary
from app.schemas import ItineraryPlan
from app.tools.registry import call_tool

if TYPE_CHECKING:
    from app.agent.graph import TravelState

logger = logging.getLogger(__name__)

# 节点间共享的 LLM 实例（由 runner 注入）
_llm: LLM | None = None


def set_llm(llm: LLM) -> None:
    global _llm
    _llm = llm


def _get_llm() -> LLM:
    if _llm is None:
        raise RuntimeError("LLM 未初始化，请先调用 set_llm()")
    return _llm


def _extract_requirements(messages: list[dict]) -> dict:
    """从**全部用户消息**中启发式抽取需求要素（目的地/天数/预算/偏好等）。

    注意：只扫描 user 消息，避免把模型追问文本里的示例值（如"3天、5天"）
    误抽成用户需求。扫全量历史，保证补充偏好时不会丢失之前已确认的要素。
    """
    import re

    req: dict = {}
    user_texts = [m.get("content", "") or "" for m in messages if m.get("role") == "user"]
    text = " ".join(user_texts)

    # 目的地：优先匹配常见城市，其次「去X / X玩 / 到X」句式
    known_cities = [
        "大理", "丽江", "成都", "北京", "上海", "杭州", "昆明", "西安",
        "重庆", "桂林", "三亚", "厦门", "苏州", "南京", "长沙", "武汉",
        "青岛", "大连", "哈尔滨", "广州", "深圳", "香港", "澳门", "台北",
        "晋江", "泉州", "福州", "厦门", "漳州", "黄山", "张家界",
    ]
    for city in known_cities:
        if city in text:
            req["destination"] = city
            break
    if "destination" not in req:
        m = re.search(r"(?:去|到|在|玩转)\s*([一-龥]{2,6}?)(?:玩|旅游|旅行|度假|住|，|,)", text)
        if m:
            req["destination"] = m.group(1)

    # 天数：X天 / X日 / X 天
    m = re.search(r"(\d+)\s*[天日]", text)
    if m:
        req["days"] = int(m.group(1))

    # 预算：XXX元 / XXX 元 / XXX块钱
    m = re.search(r"(\d+)\s*元", text)
    if m:
        req["budget"] = float(m.group(1))

    # 节奏
    if "轻松" in text or "慢" in text:
        req["pace"] = "轻松"
    elif "紧凑" in text or "赶" in text:
        req["pace"] = "紧凑"
    elif "适中" in text:
        req["pace"] = "适中"

    # 人数
    m = re.search(r"(\d+)\s*[个位]人", text)
    if m:
        req["travelers"] = f"{m.group(1)}人"

    return req


async def collect(state: TravelState) -> dict:
    """需求收集：一次 LLM 回合。有工具调用就地执行回填；无则抽需求。"""
    writer = get_stream_writer()
    llm = _get_llm()

    messages = list(state.get("messages") or [])

    # 若存在待回答的问题（从 ask_user 恢复回来），把回答追加进历史
    # 注意：ask_user 会负责追加，这里不重复处理

    result = await llm.turn(messages, tools=TOOL_DEFS, system=SYSTEM_COLLECT)

    if result.tool_calls:
        # 追加 assistant 消息（含 tool_calls）
        assistant_msg = {
            "role": "assistant",
            "content": result.content,
            "tool_calls": result.tool_calls,
        }
        messages.append(assistant_msg)

        # 就地执行工具
        for tc in result.tool_calls:
            name = tc["function"]["name"]
            args = parse_tool_arguments(tc)
            tool_result = await call_tool(name, args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(tool_result, ensure_ascii=False),
                }
            )
            writer(
                {
                    "type": "tool_result",
                    "data": {"name": name, "result": tool_result},
                }
            )

        return {"messages": messages}

    # 无工具调用：纯文本回复，抽取需求
    if result.content.strip():
        writer({"type": "agent_message", "data": {"text": result.content}})
        messages.append({"role": "assistant", "content": result.content})

    requirements = _extract_requirements(messages)
    return {"messages": messages, "requirements": requirements}


async def ask_user(state: TravelState) -> dict:
    """追问用户。全图唯一 interrupt，interrupt 前无副作用。"""
    question = state.get("pending_question") or "请问你想去哪里旅行？打算玩几天？"

    answer = interrupt({"type": "question", "question": question})

    messages = list(state.get("messages") or [])
    messages.append({"role": "user", "content": answer})

    return {"messages": messages, "pending_question": None}


async def generate(state: TravelState) -> dict:
    """生成行程：强制调用 output_itinerary。校验失败重试时注入反馈。"""
    writer = get_stream_writer()
    llm = _get_llm()

    messages = list(state.get("messages") or [])
    req = state.get("requirements") or {}

    feedback = ""
    validation = state.get("validation") or {}
    if not validation.get("ok") and validation.get("issues"):
        issues_text = "\n".join(i["message"] for i in validation["issues"] if i["level"] == "error")
        feedback = VALIDATION_FEEDBACK.format(issues=issues_text or "请检查行程结构")

    system = SYSTEM_GENERATION.format(requirements=json.dumps(req, ensure_ascii=False), feedback=feedback)
    result = await llm.turn(
        messages,
        tools=[itinerary_tool_def()],
        tool_choice={"type": "function", "function": {"name": "output_itinerary"}},
        system=system,
    )

    # 解析 output_itinerary 调用
    for tc in result.tool_calls:
        if tc["function"]["name"] == "output_itinerary":
            args = parse_tool_arguments(tc)
            try:
                plan = ItineraryPlan.model_validate(args)
                return {"itinerary": plan.model_dump()}
            except Exception as e:
                logger.warning("行程 schema 校验失败: %s", e)
                # 失败：让下一轮 generate 重试
                messages.append({"role": "assistant", "content": result.content, "tool_calls": result.tool_calls})
                messages.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": f"行程输出不符合 schema: {e}"}
                )
                state["retries"] = (state.get("retries") or 0) + 1
                return {"messages": messages, "retries": state["retries"]}

    # 模型没调 output_itinerary（异常情况），回落到文本
    if result.content.strip():
        writer({"type": "agent_message", "data": {"text": result.content}})
    messages.append({"role": "assistant", "content": result.content})
    return {"messages": messages}


async def validate(state: TravelState) -> dict:
    """合理性校验：确定式修复 + 业务校验 + 地理相邻检查。"""
    writer = get_stream_writer()
    plan = state.get("itinerary") or {}

    # 先做确定式自动修复
    report = validate_itinerary(plan)
    patched = try_auto_fix(plan, report)
    if patched is not None:
        plan = patched
        report = validate_itinerary(plan)

    # 地理相邻性检查（async，依赖 calc_transit）
    geo_issues = await check_geography(plan)
    if geo_issues:
        report.issues.extend(geo_issues)

    retries = state.get("retries") or 0
    ok = report.ok
    if not ok:
        retries += 1
        logger.info("行程校验失败（第 %d 次），问题: %s", retries, [i.message for i in report.issues if i.level == "error"])

    return {
        "itinerary": plan,
        "validation": report.asdict(),
        "retries": retries,
    }
