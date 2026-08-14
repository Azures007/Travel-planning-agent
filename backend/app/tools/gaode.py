"""高德地图 API 适配器（P2）。

接口签名与 mock_tools.py 保持一致，仅追加可选扩展字段。
真实实现抛错 → registry 降级 Mock。
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE = {
    "place": "https://restapi.amap.com/v3/place/text",
    "geocode": "https://restapi.amap.com/v3/geocode/geo",
    "driving": "https://restapi.amap.com/v3/direction/driving",
    "transit": "https://restapi.amap.com/v3/direction/transit/integrated",
    "walking": "https://restapi.amap.com/v3/direction/walking",
}


class ToolAdapterError(Exception):
    """真实 API 适配器错误，触发降级。"""


async def _get(url: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "1":
            raise ToolAdapterError(data.get("info") or "高德 API 返回失败")
        return data


async def _geocode(address: str) -> str:
    """把地点名转成 lng,lat 坐标。失败抛 ToolAdapterError。"""
    data = await _get(_BASE["geocode"], {"key": settings.amap_key, "address": address})
    geocodes = data.get("geocodes") or []
    if not geocodes:
        raise ToolAdapterError(f"地理编码失败: {address}")
    return geocodes[0].get("location") or ""


async def search_poi(destination: str, keyword: str = "") -> list[dict]:
    """搜索目的地内的地点。返回与 mock 兼容的字段 + location/address 扩展。"""
    params = {"key": settings.amap_key, "city": destination, "keywords": keyword or destination}
    data = await _get(_BASE["place"], params)
    pois = (data.get("pois") or [])[:8]
    return [
        {
            "name": p.get("name") or "",
            "category": (p.get("type") or "").split(";")[0],
            "score": 0,  # 高德无评分/门票字段，LLM 自行判断
            "open_hours": p.get("business") or "",
            "ticket": 0,
            "location": p.get("location") or "",  # lng,lat
            "address": p.get("address") or "",
        }
        for p in pois
    ]


async def calc_transit(origin: str, destination: str, mode: str = "driving") -> dict:
    """估算两地交通耗时。mode: driving/transit/walking。

    高德 direction 接口需要坐标，先地理编码把地点名转成 lng,lat 再算路径。
    """
    if mode not in ("driving", "transit", "walking"):
        mode = "driving"
    url = _BASE[mode]

    origin_loc = await _geocode(origin)
    dest_loc = await _geocode(destination)
    params = {
        "key": settings.amap_key,
        "origin": origin_loc,
        "destination": dest_loc,
    }
    # transit 模式需要 city 参数
    if mode == "transit":
        params["city"] = origin
        params["cityd"] = destination

    data = await _get(url, params)

    route = (data.get("route") or {}).get("paths") or []
    if not route:
        raise ToolAdapterError("高德未返回路径")

    path = route[0]
    duration_sec = int((path.get("duration") or "0") or 0)
    distance_m = int((path.get("distance") or "0") or 0)
    duration_min = duration_sec // 60 or 1
    distance_km = round(distance_m / 1000, 1)

    return {
        "mode": mode,
        "from": origin,
        "to": destination,
        "distance_km": distance_km,
        "duration_min": duration_min,
        "suggestion": f"{mode}约{duration_min}分钟",
        "source": "gaode",
    }
