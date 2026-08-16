"""行程编辑 API：支持修改、删除、添加活动。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import Session, Itinerary
from app.db.session import get_db

router = APIRouter(prefix="/api/edit", tags=["edit"])


class ActivityUpdate(BaseModel):
    """活动更新模型。"""
    time: str | None = None
    title: str | None = None
    location: str | None = None
    detail: str | None = None
    cost: float | None = None
    transport: str | None = None


class ActivityCreate(BaseModel):
    """活动创建模型。"""
    time: str
    title: str
    location: str | None = None
    detail: str | None = None
    cost: float = 0
    transport: str | None = None


@router.patch("/{session_id}/day/{day_index}/activity/{activity_index}")
async def update_activity(
    session_id: int,
    day_index: int,
    activity_index: int,
    update: ActivityUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新某个活动的信息。"""
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    result = await db.execute(
        select(Itinerary).where(Itinerary.session_id == session_id)
    )
    itinerary_obj = result.scalar_one_or_none()
    if not itinerary_obj:
        raise HTTPException(status_code=404, detail="未生成行程")

    itinerary = itinerary_obj.data

    # 验证索引
    if day_index < 0 or day_index >= len(itinerary.get("days", [])):
        raise HTTPException(status_code=400, detail="天数索引无效")

    day = itinerary["days"][day_index]
    activities = day.get("activities", [])

    if activity_index < 0 or activity_index >= len(activities):
        raise HTTPException(status_code=400, detail="活动索引无效")

    # 更新活动字段
    activity = activities[activity_index]
    update_data = update.model_dump(exclude_unset=True)
    activity.update(update_data)

    # 重新计算总花费
    total_cost = sum(
        act.get("cost", 0)
        for day in itinerary["days"]
        for act in day.get("activities", [])
    )
    itinerary["total_cost"] = total_cost
    itinerary["total_budget"] = total_cost  # 兼容前端字段

    # 保存
    itinerary_obj.data = itinerary
    await db.commit()

    return {"message": "活动已更新", "itinerary": itinerary}


@router.delete("/{session_id}/day/{day_index}/activity/{activity_index}")
async def delete_activity(
    session_id: int,
    day_index: int,
    activity_index: int,
    db: AsyncSession = Depends(get_db)
):
    """删除某个活动。"""
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    result = await db.execute(
        select(Itinerary).where(Itinerary.session_id == session_id)
    )
    itinerary_obj = result.scalar_one_or_none()
    if not itinerary_obj:
        raise HTTPException(status_code=404, detail="未生成行程")

    itinerary = itinerary_obj.data

    # 验证索引
    if day_index < 0 or day_index >= len(itinerary.get("days", [])):
        raise HTTPException(status_code=400, detail="天数索引无效")

    day = itinerary["days"][day_index]
    activities = day.get("activities", [])

    if activity_index < 0 or activity_index >= len(activities):
        raise HTTPException(status_code=400, detail="活动索引无效")

    # 删除活动
    del activities[activity_index]

    # 重新计算总花费
    total_cost = sum(
        act.get("cost", 0)
        for day in itinerary["days"]
        for act in day.get("activities", [])
    )
    itinerary["total_cost"] = total_cost
    itinerary["total_budget"] = total_cost

    # 保存
    itinerary_obj.data = itinerary
    await db.commit()

    return {"message": "活动已删除", "itinerary": itinerary}


@router.post("/{session_id}/day/{day_index}/activity")
async def add_activity(
    session_id: int,
    day_index: int,
    activity: ActivityCreate,
    db: AsyncSession = Depends(get_db)
):
    """在某天添加新活动。"""
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    result = await db.execute(
        select(Itinerary).where(Itinerary.session_id == session_id)
    )
    itinerary_obj = result.scalar_one_or_none()
    if not itinerary_obj:
        raise HTTPException(status_code=404, detail="未生成行程")

    itinerary = itinerary_obj.data

    # 验证索引
    if day_index < 0 or day_index >= len(itinerary.get("days", [])):
        raise HTTPException(status_code=400, detail="天数索引无效")

    day = itinerary["days"][day_index]
    activities = day.get("activities", [])

    # 添加新活动
    new_activity = activity.model_dump()
    activities.append(new_activity)

    # 重新计算总花费
    total_cost = sum(
        act.get("cost", 0)
        for day in itinerary["days"]
        for act in day.get("activities", [])
    )
    itinerary["total_cost"] = total_cost
    itinerary["total_budget"] = total_cost

    # 保存
    itinerary_obj.data = itinerary
    await db.commit()

    return {"message": "活动已添加", "itinerary": itinerary}
