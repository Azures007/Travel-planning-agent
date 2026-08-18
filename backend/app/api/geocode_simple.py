"""
地理编码 API - 使用高德地图 + 内存缓存 + 受控并发查询

优化点：
1. 内存缓存（dict）：进程级缓存，读写零延迟，避免 SQLite 在 Windows 事件循环下的阻塞问题
2. 受控并发（Semaphore）：限制并发数为 3，避免触发高德 API 的 QPS 限制
3. 失败重试：并发超限/超时时自动重试
4. 结构化错误信息：返回详细的失败原因
5. 城市+地点组合查询：解决同名地点歧义
"""
import asyncio
import logging
import os
from typing import Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter
from pydantic import BaseModel

load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")
AMAP_KEY = os.getenv("AMAP_KEY", "")

# 进程级内存缓存：{cache_key: {"lat", "lon", "display_name"}}
# 地理编码结果稳定，进程内缓存足够，重启后重新加载成本低
_GEOCODE_CACHE: Dict[str, dict] = {}


class GeocodeRequest(BaseModel):
    locations: List[str]
    destination: str


class GeocodeResult(BaseModel):
    location: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    display_name: Optional[str] = None
    cached: bool = False
    approximate: bool = False
    error: Optional[str] = None  # 结构化错误信息


async def geocode_one(
    client: httpx.AsyncClient,
    location: str,
    destination: str,
    semaphore: asyncio.Semaphore,
) -> GeocodeResult:
    """对单个地点进行地理编码（先查内存缓存，再调高德 API）。

    使用信号量限制并发，失败时自动重试（应对高德 API 并发限制）。
    """
    cache_key = f"{destination}:{location}"

    # 1. 先查内存缓存（命中直接返回，零延迟）
    cached = _GEOCODE_CACHE.get(cache_key)
    if cached:
        return GeocodeResult(
            location=location,
            lat=cached["lat"],
            lon=cached["lon"],
            display_name=cached["display_name"],
            cached=True,
        )

    # 2. 调用高德 API（用信号量限制并发 + 失败重试）
    address = f"{destination}{location}"
    params = {"key": AMAP_KEY, "address": address, "city": destination}

    max_retries = 3
    async with semaphore:
        for attempt in range(max_retries):
            try:
                response = await client.get(
                    "https://restapi.amap.com/v3/geocode/geo", params=params
                )
                if response.status_code == 200:
                    data = response.json()
                    info = data.get("info", "")

                    # 并发超限：等待后重试
                    if info == "CUQPS_HAS_EXCEEDED_THE_LIMIT":
                        if attempt < max_retries - 1:
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        return GeocodeResult(
                            location=location, error="API并发超限，请稍后重试"
                        )

                    if data.get("status") == "1" and data.get("geocodes"):
                        geocode = data["geocodes"][0]
                        loc_str = geocode.get("location", "")
                        if loc_str and "," in loc_str:
                            lon, lat = map(float, loc_str.split(","))
                            display_name = geocode.get("formatted_address", location)
                            # 写入内存缓存
                            _GEOCODE_CACHE[cache_key] = {
                                "lat": lat,
                                "lon": lon,
                                "display_name": display_name,
                            }
                            return GeocodeResult(
                                location=location,
                                lat=lat,
                                lon=lon,
                                display_name=display_name,
                            )
                        return GeocodeResult(location=location, error="未返回坐标数据")
                    return GeocodeResult(
                        location=location, error=f"高德API: {info or '无结果'}"
                    )
                return GeocodeResult(
                    location=location, error=f"HTTP {response.status_code}"
                )
            except httpx.TimeoutException:
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)
                    continue
                return GeocodeResult(location=location, error="请求超时")
            except Exception as e:
                logger.warning(f"地理编码失败: {location}, {e}")
                return GeocodeResult(location=location, error=str(e))

    return GeocodeResult(location=location, error="重试次数已用尽")


@router.post("/geocode/batch")
async def batch_geocode(request: GeocodeRequest) -> List[GeocodeResult]:
    """批量地理编码：受控并发查询 + 内存缓存。

    使用信号量限制并发数为 3，避免触发高德 API 的 QPS 限制。
    优化：如果所有地点都缓存命中，跳过创建 httpx client（避免其初始化开销）。
    """
    if not AMAP_KEY:
        return [
            GeocodeResult(location=loc, error="未配置高德API Key")
            for loc in request.locations
        ]

    # 先分离出缓存命中和未命中的地点
    results: List[Optional[GeocodeResult]] = [None] * len(request.locations)
    uncached_indices = []

    for i, loc in enumerate(request.locations):
        cache_key = f"{request.destination}:{loc}"
        cached = _GEOCODE_CACHE.get(cache_key)
        if cached:
            results[i] = GeocodeResult(
                location=loc,
                lat=cached["lat"],
                lon=cached["lon"],
                display_name=cached["display_name"],
                cached=True,
            )
        else:
            uncached_indices.append(i)

    # 全部命中缓存：直接返回，不创建 httpx client
    if not uncached_indices:
        return [r for r in results if r is not None]

    # 有未命中的地点，才创建 client 并发查询
    semaphore = asyncio.Semaphore(3)
    async with httpx.AsyncClient(timeout=8.0) as client:
        tasks = [
            geocode_one(
                client, request.locations[i], request.destination, semaphore
            )
            for i in uncached_indices
        ]
        fetched = await asyncio.gather(*tasks)

    for idx, result in zip(uncached_indices, fetched):
        results[idx] = result

    return [r for r in results if r is not None]


@router.get("/geocode/cache/stats")
async def cache_stats():
    """查看缓存统计（调试用）。"""
    return {"cached_locations": len(_GEOCODE_CACHE)}
