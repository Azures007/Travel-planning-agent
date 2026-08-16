"""
简化的地理编码 API - 只使用高德地图，无缓存
"""
from fastapi import APIRouter
from pydantic import BaseModel
import httpx
from typing import List, Optional
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api")
AMAP_KEY = os.getenv('AMAP_KEY', '')


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


@router.post("/geocode/batch")
async def batch_geocode(request: GeocodeRequest) -> List[GeocodeResult]:
    """批量地理编码，使用高德地图 API"""
    results = []

    if not AMAP_KEY:
        # 没有 API key，返回空结果
        return [GeocodeResult(location=loc) for loc in request.locations]

    async with httpx.AsyncClient(timeout=5.0) as client:
        for location in request.locations:
            # 组合查询：城市+地点
            address = f"{request.destination}{location}"
            params = {
                'key': AMAP_KEY,
                'address': address,
                'city': request.destination
            }

            try:
                response = await client.get(
                    'https://restapi.amap.com/v3/geocode/geo',
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == '1' and data.get('geocodes'):
                        geocode = data['geocodes'][0]
                        loc_str = geocode.get('location', '')
                        if loc_str and ',' in loc_str:
                            lon, lat = map(float, loc_str.split(','))
                            results.append(GeocodeResult(
                                location=location,
                                lat=lat,
                                lon=lon,
                                display_name=geocode.get('formatted_address', location)
                            ))
                            continue
            except Exception as e:
                print(f"地理编码失败: {location}, {e}")

            # 失败时返回空结果
            results.append(GeocodeResult(location=location))

    return results
