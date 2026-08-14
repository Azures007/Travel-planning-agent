"""行程合理性校验器（P2）。

规则覆盖：天数编号、活动数、花费非负、字段完整、时间顺序、预算一致性、地理相邻。
确定式问题自动修复；其余走重新生成。
"""

import asyncio
from dataclasses import dataclass, field


@dataclass
class Issue:
    rule: str
    level: str  # error / warning
    message: str

    def asdict(self) -> dict:
        return {"rule": self.rule, "level": self.level, "message": self.message}


@dataclass
class ValidationReport:
    ok: bool
    issues: list[Issue] = field(default_factory=list)

    def asdict(self) -> dict:
        return {
            "ok": self.ok,
            "issues": [i.asdict() for i in self.issues],
            "errors": sum(1 for i in self.issues if i.level == "error"),
        }


def _normalize_time(t: str) -> int:
    """把 '09:00-11:00' 或 '09:00' 转成分钟数，用于顺序比较。失败返回 -1。"""
    try:
        start = t.split("-")[0].strip().split(":")[:2]
        return int(start[0]) * 60 + int(start[1])
    except (ValueError, IndexError):
        return -1


async def _transit_duration_async(origin: str, destination: str) -> int | None:
    """异步估算交通耗时，供 validate 节点在事件循环内使用。"""
    try:
        from app.tools.registry import call_tool

        result = await call_tool("calc_transit", {"origin": origin, "destination": destination})
        if result.get("_degraded") or result.get("error"):
            return None
        return int(result.get("duration_min") or 0)
    except Exception:
        return None


async def check_geography(plan: dict) -> list[Issue]:
    """地理相邻性检查（async）。逐日相邻活动调 calc_transit。"""
    issues: list[Issue] = []
    days = plan.get("days") or []
    for i, d in enumerate(days[:-1]):
        acts = d.get("activities") or []
        next_acts = days[i + 1].get("activities") or []
        if not acts or not next_acts:
            continue
        last_loc = acts[-1].get("location")
        first_next = next_acts[0].get("location")
        if last_loc and first_next:
            dur = await _transit_duration_async(last_loc, first_next)
            if dur is not None:
                if dur > 120:
                    issues.append(Issue("geography", "error", f"第{d.get('day')}天末到第{i+2}天首站交通耗时约{dur}分钟，可能跨区域过远"))
                elif dur > 90:
                    issues.append(Issue("geography", "warning", f"第{d.get('day')}天末到第{i+2}天首站交通耗时约{dur}分钟"))
    return issues


def validate_itinerary(plan: dict) -> ValidationReport:
    """校验行程结构。地理相邻性检查由 check_geography 异步执行。"""
    issues: list[Issue] = []

    days = plan.get("days") or []
    if not days:
        issues.append(Issue("days", "error", "行程没有任何天数安排"))
        return ValidationReport(ok=False, issues=issues)

    # 1. 天数编号：从 1 连续递增，无重复
    seen: set[int] = set()
    for i, d in enumerate(days):
        day_num = d.get("day")
        if not isinstance(day_num, int) or day_num < 1:
            issues.append(Issue("day_index", "error", f"第{i+1}天编号不合法: {day_num}"))
            continue
        if day_num in seen:
            issues.append(Issue("day_index", "error", f"天数 {day_num} 重复"))
        seen.add(day_num)
    expected = list(range(1, len(days) + 1))
    actual = [d.get("day") for d in days if isinstance(d.get("day"), int)]
    if actual != expected:
        issues.append(Issue("day_index", "error", f"天数编号应从 1 连续递增，当前为 {actual}"))

    # 2. 每日活动数
    total_cost = 0.0
    for d in days:
        acts = d.get("activities") or []
        n = len(acts)
        if n < 1:
            issues.append(Issue("activity_count", "error", f"第{d.get('day')}天没有安排活动"))
        elif n > 7:
            issues.append(Issue("activity_count", "error", f"第{d.get('day')}天活动过多({n}个)，应控制在 3-5 个"))
        elif n < 3:
            issues.append(Issue("activity_count", "warning", f"第{d.get('day')}天活动偏少({n}个)"))
        elif n > 5:
            issues.append(Issue("activity_count", "warning", f"第{d.get('day')}天活动偏多({n}个)，可能过赶"))

        # 3. 字段完整 + 花费非负 + 时间顺序
        prev_time = -1
        for act in acts:
            title, location = act.get("title") or "", act.get("location") or ""
            t = act.get("time") or ""
            if not title or not location or not t:
                issues.append(Issue("field_complete", "error", f"第{d.get('day')}天有活动缺少 title/location/time"))
            cost = act.get("cost") or 0
            if isinstance(cost, (int, float)) and cost < 0:
                issues.append(Issue("cost", "error", f"活动「{title}」花费为负数"))
                total_cost += 0
            else:
                total_cost += float(cost)

            cur = _normalize_time(t)
            if cur >= 0 and cur < prev_time:
                issues.append(Issue("time_order", "warning", f"第{d.get('day')}天活动时间顺序不当: {t}"))
            prev_time = cur

        day_cost = d.get("day_cost") or 0
        if isinstance(day_cost, (int, float)) and day_cost < 0:
            issues.append(Issue("cost", "error", f"第{d.get('day')}天花费为负数"))

    # 5. 预算一致性
    budget = plan.get("total_budget") or 0
    if isinstance(budget, (int, float)) and budget < 0:
        issues.append(Issue("cost", "error", "总预算为负数"))
    if total_cost > 0 and budget > 0:
        deviation = abs(total_cost - budget) / budget
        if deviation > 0.2:
            issues.append(
                Issue("budget", "warning", f"各天花费合计({total_cost})与总预算({budget})偏差 {deviation:.0%}")
            )

    # 需求预算 vs 行程总预算：用户设定预算若远高于行程内花费，给出说明性提示
    req = plan.get("requirements") or {}
    user_budget = req.get("budget")
    if user_budget and budget > 0 and user_budget > budget * 1.5:
        issues.append(
            Issue(
                "budget",
                "warning",
                f"行程内花费约{budget}元，低于您设定的预算{user_budget}元（差额通常用于住宿和往返大交通）",
            )
        )

    return ValidationReport(ok=not any(i.level == "error" for i in issues), issues=issues)


def try_auto_fix(plan: dict, report: ValidationReport) -> dict | None:
    """确定式自动修复：负数清零、天数重编号。返回修复后的 plan，无可修复项返回 None。"""
    fixed = False
    days = plan.get("days") or []

    # 负数清零
    for i, d in enumerate(days):
        acts = d.get("activities") or []
        for act in acts:
            if isinstance(act.get("cost"), (int, float)) and act["cost"] < 0:
                act["cost"] = 0.0
                fixed = True
        if isinstance(d.get("day_cost"), (int, float)) and d["day_cost"] < 0:
            d["day_cost"] = 0.0
            fixed = True
    if isinstance(plan.get("total_budget"), (int, float)) and plan["total_budget"] < 0:
        plan["total_budget"] = 0.0
        fixed = True

    # 天数重编号：按出现顺序 1,2,3...
    for i, d in enumerate(days):
        if d.get("day") != i + 1:
            d["day"] = i + 1
            fixed = True

    if not fixed:
        return None
    return plan
