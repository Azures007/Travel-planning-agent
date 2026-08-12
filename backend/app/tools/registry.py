"""工具实现注册表：按 Key 选择真实 API 或 Mock，失败自动降级。

真实实现抛错（网络/配额/HTTP 错误）时，自动回退到 Mock 并在结果中
带 _degraded 标记（行为可见），同时记录 warning 日志。
"""

import asyncio
import inspect
import logging

from app.config import settings
from app.tools import gaode, mock_tools, qweather

logger = logging.getLogger(__name__)


def get_search_poi():
    if settings.force_mock_tools or not settings.amap_key:
        return mock_tools.search_poi
    return gaode.search_poi


def get_calc_transit():
    if settings.force_mock_tools or not settings.amap_key:
        return mock_tools.calc_transit
    return gaode.calc_transit


def get_weather():
    if settings.force_mock_tools or not settings.qweather_key:
        return mock_tools.get_weather
    return qweather.get_weather


_TOOL_GETTERS = {
    "search_poi": get_search_poi,
    "calc_transit": get_calc_transit,
    "get_weather": get_weather,
}

_MOCK_FALLBACK = {
    "search_poi": mock_tools.search_poi,
    "calc_transit": mock_tools.calc_transit,
    "get_weather": mock_tools.get_weather,
}


async def _run(fn, **kwargs):
    """兼容 sync/async 工具实现。"""
    if inspect.iscoroutinefunction(fn):
        return await fn(**kwargs)
    return await asyncio.to_thread(fn, **kwargs)


async def call_tool(name: str, arguments: dict) -> dict:
    """执行工具调用：真实实现优先，失败自动降级 Mock。"""
    getter = _TOOL_GETTERS.get(name)
    if getter is None:
        return {"error": f"未知工具: {name}"}

    fn = getter()
    mock = _MOCK_FALLBACK.get(name)

    try:
        result = await _run(fn, **arguments)
        return result if isinstance(result, dict) else {"result": result}
    except Exception as e:
        # 真实实现失败 → 降级 Mock
        logger.warning("工具 %s 真实实现失败(%s: %s)，降级 Mock", name, type(e).__name__, e)
        if mock is not None:
            try:
                fallback = await _run(mock, **arguments)
                return {
                    **fallback,
                    "_degraded": True,
                    "reason": f"{type(e).__name__}: {e}",
                }
            except Exception as e2:
                return {"error": f"工具 {name} 执行失败: {e2}"}
        return {"error": f"工具 {name} 执行失败: {e}"}
