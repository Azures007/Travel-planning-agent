from pydantic import BaseModel, Field


class Activity(BaseModel):
    """单个活动条目（一个时间段内做的一件事）"""
    time: str = Field(description="时间段，如 09:00-11:00")
    title: str = Field(description="活动名称，如 大理古城")
    location: str = Field(description="地点名称")
    detail: str = Field(default="", description="活动说明/推荐理由")
    transport: str = Field(default="", description="前往方式")
    cost: float = Field(default=0, description="预估花费（人民币）")


class DayPlan(BaseModel):
    """一天的行程安排"""
    day: int = Field(description="第几天，从 1 开始")
    date: str = Field(default="", description="日期或占位描述，如 第1天")
    summary: str = Field(default="", description="当日行程概述")
    activities: list[Activity] = Field(description="当天活动列表，按时间排序")
    day_cost: float = Field(default=0, description="当日预估总花费")


class TripRequirements(BaseModel):
    """从对话中提取的旅行需求要素"""
    destination: str = Field(default="", description="目的地")
    days: int | None = Field(default=None, description="行程天数")
    budget: float | None = Field(default=None, description="总预算（元）")
    travelers: str = Field(default="", description="出行人员，如 2大人1小孩")
    pace: str = Field(default="", description="节奏偏好：轻松/适中/紧凑")
    preferences: str = Field(default="", description="兴趣偏好，如 美食/自然/人文")
    departure_date: str = Field(default="", description="出发日期，如 8月15日 或 下周五")
    special_notes: str = Field(default="", description="其他要求，如 带老人/不爬山")


class ItineraryPlan(BaseModel):
    """完整行程计划"""
    title: str = Field(description="行程标题，如 大理5日深度游")
    requirements: TripRequirements = Field(description="本次规划的需求要素")
    total_budget: float = Field(default=0, description="总预算估算")
    days: list[DayPlan] = Field(description="逐日活动安排")
