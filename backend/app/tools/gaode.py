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
    """估算两地交通耗时。mode: driving/transit/walking。"""
    if mode not in ("driving", "transit", "walking"):
        mode = "driving"
    url = _BASE[mode]
    params = {"key": settings.amap_key, "origin": "0,0", "destination": "0,0"}
    # 高德 direction 接口需要坐标，这里先用名称做地理编码兜底失败。
    # P2 增强：接入 geo/geocode 先转坐标再算路径。
    try:
        data = await _get(url, params)
    except ToolAdapterError:
        raise
    except Exception:
        raise

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
