"""Mock 数据工具：P1 阶段用模拟数据跑通闭环，P2 替换为高德/和风真实 API。

所有工具的接口签名保持与真实实现一致，方便无缝切换。
"""

import datetime


def _season():
    month = datetime.date.today().month
    return "夏季" if month in (6, 7, 8) else "冬季" if month in (12, 1, 2) else "春秋季"


# 常用旅游目的地预置地点池，模拟真实 POI 查询结果
_POI_POOL: dict[str, list[dict]] = {
    "大理": [
        {"name": "大理古城", "category": "历史街区", "score": 4.8, "open_hours": "全天开放", "ticket": 0},
        {"name": "洱海", "category": "自然风光", "score": 4.9, "open_hours": "全天开放", "ticket": 0},
        {"name": "苍山", "category": "自然风光", "score": 4.7, "open_hours": "08:30-16:00", "ticket": 40},
        {"name": "崇圣寺三塔", "category": "人文古迹", "score": 4.7, "open_hours": "08:00-18:00", "ticket": 75},
        {"name": "喜洲古镇", "category": "古镇村落", "score": 4.6, "open_hours": "全天开放", "ticket": 0},
        {"name": "双廊古镇", "category": "古镇村落", "score": 4.6, "open_hours": "全天开放", "ticket": 0},
        {"name": "海舌公园", "category": "自然风光", "score": 4.5, "open_hours": "08:00-18:00", "ticket": 0},
        {"name": "才村码头", "category": "自然风光", "score": 4.4, "open_hours": "全天开放", "ticket": 0},
    ],
    "丽江": [
        {"name": "丽江古城", "category": "历史街区", "score": 4.7, "open_hours": "全天开放", "ticket": 0},
        {"name": "玉龙雪山", "category": "自然风光", "score": 4.9, "open_hours": "07:00-16:00", "ticket": 100},
        {"name": "束河古镇", "category": "古镇村落", "score": 4.5, "open_hours": "全天开放", "ticket": 0},
        {"name": "拉市海", "category": "自然风光", "score": 4.4, "open_hours": "08:00-18:00", "ticket": 30},
        {"name": "黑龙潭公园", "category": "自然风光", "score": 4.5, "open_hours": "07:00-19:00", "ticket": 0},
    ],
    "成都": [
        {"name": "宽窄巷子", "category": "历史街区", "score": 4.6, "open_hours": "全天开放", "ticket": 0},
        {"name": "大熊猫繁育研究基地", "category": "主题公园", "score": 4.8, "open_hours": "07:30-18:00", "ticket": 55},
        {"name": "武侯祠", "category": "人文古迹", "score": 4.6, "open_hours": "08:00-18:30", "ticket": 50},
        {"name": "锦里", "category": "历史街区", "score": 4.5, "open_hours": "全天开放", "ticket": 0},
        {"name": "都江堰", "category": "人文古迹", "score": 4.8, "open_hours": "08:00-18:00", "ticket": 80},
        {"name": "青城山", "category": "自然风光", "score": 4.7, "open_hours": "08:00-17:00", "ticket": 80},
    ],
    "北京": [
        {"name": "故宫博物院", "category": "人文古迹", "score": 4.9, "open_hours": "08:30-17:00", "ticket": 60},
        {"name": "天安门广场", "category": "人文古迹", "score": 4.8, "open_hours": "全天开放", "ticket": 0},
        {"name": "颐和园", "category": "人文古迹", "score": 4.8, "open_hours": "06:30-18:00", "ticket": 30},
        {"name": "长城(八达岭)", "category": "自然风光", "score": 4.8, "open_hours": "07:00-18:00", "ticket": 40},
        {"name": "天坛公园", "category": "人文古迹", "score": 4.7, "open_hours": "06:00-22:00", "ticket": 15},
    ],
    "上海": [
        {"name": "外滩", "category": "自然风光", "score": 4.8, "open_hours": "全天开放", "ticket": 0},
        {"name": "东方明珠", "category": "现代建筑", "score": 4.6, "open_hours": "09:00-21:00", "ticket": 220},
        {"name": "豫园", "category": "人文古迹", "score": 4.6, "open_hours": "09:00-16:30", "ticket": 40},
        {"name": "迪士尼乐园", "category": "主题公园", "score": 4.8, "open_hours": "08:30-20:30", "ticket": 475},
    ],
    "杭州": [
        {"name": "西湖", "category": "自然风光", "score": 4.9, "open_hours": "全天开放", "ticket": 0},
        {"name": "灵隐寺", "category": "人文古迹", "score": 4.7, "open_hours": "07:00-18:00", "ticket": 45},
        {"name": "西溪湿地", "category": "自然风光", "score": 4.6, "open_hours": "08:00-17:30", "ticket": 80},
        {"name": "雷峰塔", "category": "人文古迹", "score": 4.5, "open_hours": "08:00-20:00", "ticket": 40},
    ],
}

# 通用地点池：目标不在池内时用于兜底
_GENERIC_POOL: list[dict] = [
    {"name": "城市中心景区", "category": "综合景区", "score": 4.5, "open_hours": "08:00-18:00", "ticket": 0},
    {"name": "历史文化街区", "category": "历史街区", "score": 4.6, "open_hours": "全天开放", "ticket": 0},
    {"name": "城市公园", "category": "自然风光", "score": 4.4, "open_hours": "06:00-22:00", "ticket": 0},
    {"name": "博物馆", "category": "人文古迹", "score": 4.5, "open_hours": "09:00-17:00", "ticket": 30},
]


def search_poi(destination: str, keyword: str = "") -> list[dict]:
    """模拟高德 POI 搜索。返回地点列表，含名称/分类/评分/开放时间/门票。"""
    pool = _POI_POOL.get(destination, _GENERIC_POOL)
    results = []
    for p in pool:
        if not keyword or keyword.lower() in p["name"].lower():
            results.append(
                {
                    "name": p["name"],
                    "category": p["category"],
                    "score": p["score"],
                    "open_hours": p["open_hours"],
                    "ticket": p["ticket"],
                }
            )
    return results[:8]


def get_weather(destination: str, days: int = 5) -> dict:
    """模拟和风天气逐日预报。返回季节 + 每日天气列表。"""
    season = _season()
    conditions = {
        "夏季": ["晴", "晴", "多云", "阵雨", "晴"],
        "冬季": ["晴", "多云", "晴", "阴", "多云"],
    }.get(season, ["晴", "多云", "晴", "多云", "晴"])
    daily = [
        {
            "date": f"第{i+1}天",
            "condition": conditions[i % len(conditions)],
            "temp_high": 24 + (i % 5),
            "temp_low": 14 + (i % 4),
            "note": "适宜出行" if conditions[i % len(conditions)] in ("晴", "多云") else "建议带伞",
        }
        for i in range(min(days, 7))
    ]
    return {"destination": destination, "season": season, "daily": daily}


def calc_transit(origin: str, destination: str, mode: str = "driving") -> dict:
    """模拟高德路径规划。返回交通方式、距离与耗时。"""
    _dist_km = abs(hash(origin + destination) % 40) + 3  # 3~42 km 确定性伪随机
    _duration_min = int(_dist_km * (2 if mode == "driving" else 4)) + 15
    return {
        "mode": mode,
        "from": origin,
        "to": destination,
        "distance_km": _dist_km,
        "duration_min": _duration_min,
        "suggestion": f"{mode}约{_duration_min}分钟",
    }
