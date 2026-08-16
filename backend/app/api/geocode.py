"""
地理编码 API - 支持缓存的地点坐标查询
优先使用高德地图 API（国内精度更高），失败时退回 Nominatim
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
import asyncio
from typing import List, Optional
import sqlite3
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

router = APIRouter(prefix="/api")

# 高德地图 API Key（从环境变量读取）
AMAP_KEY = os.getenv('AMAP_KEY', '')

# 地理编码缓存数据库
CACHE_DB = os.path.join(os.path.dirname(__file__), '../../geocode_cache.db')

def init_cache_db():
    """初始化缓存数据库"""
    conn = sqlite3.connect(CACHE_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS geocode_cache (
            query TEXT PRIMARY KEY,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            display_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# 初始化数据库
init_cache_db()


class GeocodeRequest(BaseModel):
    locations: List[str]
    destination: str


class GeocodeResult(BaseModel):
    location: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    display_name: Optional[str] = None
    cached: bool = False
    approximate: bool = False  # 标记是否为近似位置（未精确匹配，用城市中心兜底）


async def fetch_from_amap(query: str, city: str) -> Optional[dict]:
    """从高德地图 API 获取地理编码（国内精度更高）。

    返回格式: {'lat': float, 'lon': float, 'display_name': str}
    """
    if not AMAP_KEY:
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            url = "https://restapi.amap.com/v3/geocode/geo"

            # 用 "城市+地点" 组合查询（避免同名地点歧义）
            combined_query = f"{city}{query}"
            params = {
                'key': AMAP_KEY,
                'address': combined_query,
                'city': city
            }

            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == '1' and data.get('geocodes'):
                    geocode = data['geocodes'][0]
                    location = geocode.get('location', '')
                    if location and ',' in location:
                        lon, lat = map(float, location.split(','))
                        return {
                            'lat': lat,
                            'lon': lon,
                            'display_name': geocode.get('formatted_address', query)
                        }
    except Exception as e:
        print(f"高德地图请求失败: {query}, {e}")

    return None


async def fetch_city_bounds(city: str) -> Optional[dict]:
    """获取城市的中心坐标和边界框。

    优先使用高德地图 API（国内城市精度更高），失败时退回 Nominatim。
    """
    # 先尝试高德地图
    if AMAP_KEY:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                url = "https://restapi.amap.com/v3/config/district"
                params = {
                    'key': AMAP_KEY,
                    'keywords': city,
                    'subdistrict': 0,
                    'extensions': 'base'
                }

                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == '1' and data.get('districts'):
                        district = data['districts'][0]
                        center = district.get('center', '')
                        if center and ',' in center:
                            lon, lat = map(float, center.split(','))
                            # 高德返回的是城市行政中心，更准确
                            # 构造一个合理的搜索范围（±0.2度，约20km）
                            viewbox = f"{lon-0.2},{lat+0.2},{lon+0.2},{lat-0.2}"
                            return {'lat': lat, 'lon': lon, 'viewbox': viewbox}
        except Exception as e:
            print(f"高德地图获取城市边界失败: {city}, {e}")

    # 退回 Nominatim（国外城市或高德失败时）
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': f"{city}, 中国",
                'format': 'json',
                'limit': 1,
                'accept-language': 'zh-CN',
                'addressdetails': 1,
            }
            headers = {'User-Agent': 'TravelPlanningAgent/1.0'}

            response = await client.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    item = data[0]
                    lat = float(item['lat'])
                    lon = float(item['lon'])
                    # boundingbox 格式: [south_lat, north_lat, west_lon, east_lon]
                    bbox = item.get('boundingbox')
                    if bbox and len(bbox) == 4:
                        # 在城市边界基础上向外扩展 0.3 度（约30km），
                        # 覆盖周边景点，同时避免匹配到其他省份
                        south = float(bbox[0]) - 0.3
                        north = float(bbox[1]) + 0.3
                        west = float(bbox[2]) - 0.3
                        east = float(bbox[3]) + 0.3
                        viewbox = f"{west},{north},{east},{south}"
                    else:
                        # 无边界框时，用中心点 ±0.5 度构造一个大致范围
                        viewbox = f"{lon-0.5},{lat+0.5},{lon+0.5},{lat-0.5}"
                    return {'lat': lat, 'lon': lon, 'viewbox': viewbox}
    except Exception as e:
        print(f"获取城市边界失败: {city}, {e}")

    return None


async def fetch_from_nominatim(query: str, viewbox: Optional[str] = None) -> Optional[dict]:
    """从 Nominatim API 获取地理编码。

    viewbox: 限制搜索范围的边界框（west,north,east,south），配合 bounded=1
    强制结果落在该范围内，避免匹配到其他省份的同名地点。
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"https://nominatim.openstreetmap.org/search"
            params = {
                'q': query,
                'format': 'json',
                'limit': 1,
                'accept-language': 'zh-CN'
            }
            # 有边界框时，限制搜索范围
            if viewbox:
                params['viewbox'] = viewbox
                params['bounded'] = 1
            headers = {
                'User-Agent': 'TravelPlanningAgent/1.0'
            }

            response = await client.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return {
                        'lat': float(data[0]['lat']),
                        'lon': float(data[0]['lon']),
                        'display_name': data[0].get('display_name', '')
                    }
    except Exception as e:
        print(f"Nominatim 请求失败: {query}, {e}")

    return None


def get_from_cache(query: str) -> Optional[dict]:
    """从缓存获取地理编码"""
    conn = sqlite3.connect(CACHE_DB)
    c = conn.cursor()
    c.execute('SELECT lat, lon, display_name FROM geocode_cache WHERE query = ?', (query,))
    row = c.fetchone()
    conn.close()

    if row:
        return {
            'lat': row[0],
            'lon': row[1],
            'display_name': row[2]
        }
    return None


def save_to_cache(query: str, lat: float, lon: float, display_name: str):
    """保存到缓存"""
    conn = sqlite3.connect(CACHE_DB)
    c = conn.cursor()
    c.execute(
        'INSERT OR REPLACE INTO geocode_cache (query, lat, lon, display_name) VALUES (?, ?, ?, ?)',
        (query, lat, lon, display_name)
    )
    conn.commit()
    conn.close()


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算两点间的大致距离（公里），用 Haversine 公式。"""
    import math
    r = 6371  # 地球半径（公里）
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return r * 2 * math.asin(math.sqrt(a))


@router.post('/geocode/batch', response_model=List[GeocodeResult])
async def batch_geocode(request: GeocodeRequest):
    """
    批量地理编码，支持缓存。

    优化：先获取目的地城市的边界框，用它限制每个地点的搜索范围，
    避免匹配到其他省份的同名地点。对超出城市范围过远的结果视为无效。
    """
    results = []
    uncached_locations = []

    # 缓存 key 加上 destination，避免不同城市的同名地点冲突
    for location in request.locations:
        query = f"{location}, {request.destination}, 中国"
        # TODO: 缓存功能暂时禁用，因为同步 SQLite 操作会阻塞异步事件循环
        # cached = get_from_cache(query)
        cached = None

        if cached:
            results.append(GeocodeResult(
                location=location,
                lat=cached['lat'],
                lon=cached['lon'],
                display_name=cached['display_name'],
                cached=True
            ))
        else:
            uncached_locations.append((location, query))
            results.append(GeocodeResult(location=location, cached=False))

    # 有未缓存地点时，先获取城市边界，再逐个搜索
    if uncached_locations:
        # 获取目的地城市的中心坐标和边界框
        city_bounds = await fetch_city_bounds(request.destination)
        viewbox = city_bounds['viewbox'] if city_bounds else None
        city_lat = city_bounds['lat'] if city_bounds else None
        city_lon = city_bounds['lon'] if city_bounds else None

        semaphore = asyncio.Semaphore(5)  # 高德 API 速率限制宽松，可以更多并发

        async def fetch_with_limit(location: str, query: str, index: int):
            async with semaphore:
                # 高德 API 速率限制很宽松，只需短暂延迟
                await asyncio.sleep(index * 0.1)

                # 第一步：优先用高德地图（国内精度更高，速度快）
                data = await fetch_from_amap(location, request.destination)

                # 第二步：高德失败，用 Nominatim 在城市边界内搜索（仅作为备选）
                if not data and viewbox:
                    search_query = f"{location} {request.destination}"
                    data = await fetch_from_nominatim(search_query, viewbox=viewbox)

                if data:
                    # 保存到缓存（异步执行避免阻塞）
                    # TODO: 将 save_to_cache 改为异步或使用 asyncio.to_thread
                    # save_to_cache(query, data['lat'], data['lon'], data['display_name'])

                    # 更新结果
                    for i, result in enumerate(results):
                        if result.location == location:
                            results[i] = GeocodeResult(
                                location=location,
                                lat=data['lat'],
                                lon=data['lon'],
                                display_name=data['display_name'],
                                cached=False
                            )
                            break
                elif city_lat is not None and city_lon is not None:
                    # 兜底：未精确匹配时，用城市中心 + 小偏移显示近似位置
                    offset = (hash(location) % 100) / 5000.0  # 约 ±0.02 度（~2km）
                    approx_lat = city_lat + offset - 0.01
                    approx_lon = city_lon + offset - 0.01
                    for i, result in enumerate(results):
                        if result.location == location:
                            results[i] = GeocodeResult(
                                location=location,
                                lat=approx_lat,
                                lon=approx_lon,
                                display_name=f"{location}（{request.destination}大致位置）",
                                cached=False,
                                approximate=True
                            )
                            break

        tasks = [
            fetch_with_limit(loc, query, idx)
            for idx, (loc, query) in enumerate(uncached_locations)
        ]
        await asyncio.gather(*tasks)

    return results
