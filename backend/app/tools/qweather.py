"""和风天气 API 适配器（P2）。

两步式：geoapi city/lookup 取 location id → devapi v7/weather/3d 逐日预报。
真实实现抛错 → registry 降级 Mock。
"""

import datetime
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# 和风 2026 起必须用账号专属 Host，域名从配置读取（公共域名已废弃）
_GEO_URL = lambda: f"{settings.qweather_geo_host}/v2/city/lookup"
_WEATHER_URL = lambda: f"{settings.qweather_host}/v7/weather/3d"


class ToolAdapterError(Exception):
    """真实 API 适配器错误，触发降级。"""


async def _lookup_location_id(city: str) -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_GEO_URL(), params={"key": settings.qweather_key, "location": city})
        resp.raise_for_status()
        data = resp.json()
    if data.get("code") != "200" or not data.get("location"):
        raise ToolAdapterError(data.get("code") or "和风地理编码失败")
    return data["location"][0]["id"]


async def _get_weather(location_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_WEATHER_URL(), params={"key": settings.qweather_key, "location": location_id})
        resp.raise_for_status()
        data = resp.json()
    if data.get("code") != "200":
        raise ToolAdapterError(data.get("code") or "和风天气查询失败")
    return data.get("daily") or []


def _season() -> str:
    month = datetime.date.today().month
    return "夏季" if month in (6, 7, 8) else "冬季" if month in (12, 1, 2) else "春秋季"


async def get_weather(destination: str, days: int = 5) -> dict:
    """查询目的地未来几天的天气。保持与 mock 兼容的返回结构。"""
    location_id = await _lookup_location_id(destination)
    daily_raw = await _get_weather(location_id)

    # 和风免费版仅 3 天；截断并按可用天数返回
    daily = []
    for i, d in enumerate(daily_raw[: max(days, 1)]):
        condition = d.get("textDay") or d.get("text") or ""
        note = "适宜出行" if condition in ("晴", "多云") else "建议带伞"
        daily.append(
            {
                "date": d.get("fxDate") or f"第{i+1}天",
                "condition": condition,
                "temp_high": int(d.get("tempMax") or 0),
                "temp_low": int(d.get("tempMin") or 0),
                "note": note,
            }
        )

    return {
        "destination": destination,
        "season": _season(),
        "daily": daily,
        "source": "qweather",
    }
