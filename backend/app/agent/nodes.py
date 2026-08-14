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

    # 预算：XXX元 / XXX 元 / 预算XXX / XXX块钱
    m = re.search(r"(\d+)\s*元|预算\s*(\d+)|(\d+)\s*块钱", text)
    if m:
        budget_str = next(g for g in m.groups() if g)
        req["budget"] = float(budget_str)

    # 节奏
    if "轻松" in text or "慢" in text:
        req["pace"] = "轻松"
    elif "紧凑" in text or "赶" in text:
        req["pace"] = "紧凑"
    elif "适中" in text:
        req["pace"] = "适中"

    # 人数：2个人 / 两个人 / 一家三口 / 3人
    m = re.search(r"(\d+|[一二两三四五六七八九十]+)\s*[个位]人", text)
    if m:
        num_map = {"一": "1", "两": "2", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}
        raw = m.group(1)
        travelers = num_map.get(raw, raw)
        req["travelers"] = f"{travelers}人"

    # 出发日期：8月15号 / 8月15日 / 15号 / 下周五
    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[号日]", text)
    if m:
        req["departure_date"] = f"{m.group(1)}月{m.group(2)}日"
    else:
        m = re.search(r"(今天|明天|后天|下周[一二三四五六日天]|下周末|这个周末)", text)
        if m:
            req["departure_date"] = m.group(1)

    # 兴趣偏好：从关键词识别
    pref_keywords = {
        "美食": ["美食", "吃", "好吃", "小吃", "吃货"],
        "自然风光": ["自然", "风景", "山水", "海边", "海滩", "森林", "爬山"],
        "人文历史": ["历史", "古迹", "文化", "博物馆", "古镇", "人文"],
        "摄影": ["摄影", "拍照", "出片", "拍照片"],
        "亲子": ["亲子", "小孩", "孩子", "带娃"],
        "购物": ["购物", "逛街", "买"],
        "休闲度假": ["放松", "度假", "休闲", "发呆"],
    }
    found_prefs = [label for label, kws in pref_keywords.items() if any(k in text for k in kws)]
    if found_prefs:
        req["preferences"] = "、".join(found_prefs)

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

        # 工具调用轮也同步抽取需求，保证已确认字段不丢、随时可用
        new_requirements = _extract_requirements(messages)
        requirements = _merge_requirements(state.get("requirements"), new_requirements)

        return {"messages": messages, "requirements": requirements}

    # 无工具调用：纯文本回复，抽取需求
    if result.content.strip():
        writer({"type": "agent_message", "data": {"text": result.content}})
        messages.append({"role": "assistant", "content": result.content})

    # 跨轮累积：新抽取的需求与已有需求合并，已确认的字段不被冲掉
    new_requirements = _extract_requirements(messages)
    requirements = _merge_requirements(state.get("requirements"), new_requirements)

    # 计算缺失的必问字段并设置待问问题（由 ask_user 节点消费）
    # 注意：必须在节点内返回更新 state，路由函数不能直接改 state
    from app.agent.graph import FIELD_QUESTIONS, missing_fields

    missing = missing_fields(requirements)
    pending_question = " ".join(FIELD_QUESTIONS[f] for f in missing) if missing else None

    return {
        "messages": messages,
        "requirements": requirements,
        "pending_question": pending_question,
    }


def _merge_requirements(prev: dict | None, new: dict | None) -> dict:
    """合并新旧需求：新值覆盖旧值，但旧值若新抽取没提取到则保留。

    这样用户后续补充偏好（如「住市区，喜欢美食」）时，不会把之前
    已确认的目的地/天数/预算冲掉。
    """
    merged: dict = {}
    if prev:
        merged.update(prev)
    if new:
        for k, v in new.items():
            if v:  # 新值非空才覆盖（空值保留旧值）
                merged[k] = v
    return merged


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

    # 保险：若 requirements 为空（理论上 collect 已算好），现场从历史抽取
    if not req:
        req = _extract_requirements(messages)

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
