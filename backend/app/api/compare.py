"""行程方案对比 API：生成多个不同风格的方案供用户选择。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import Session, Itinerary
from app.db.session import get_db
from app.agent.runner import AgentRunner
from app.agent.llm import LLM
from app.config import settings

router = APIRouter(prefix="/api/compare", tags=["compare"])


class GenerateAlternativesRequest(BaseModel):
    """生成备选方案请求。"""
    session_id: int
    styles: list[str] = ["预算型", "舒适型", "豪华型"]  # 可选风格


def _make_llm() -> LLM:
    return LLM(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        model=settings.dashscope_model,
    )


@router.post("/generate-alternatives")
async def generate_alternatives(
    req: GenerateAlternativesRequest,
    db: AsyncSession = Depends(get_db)
):
    """基于当前行程生成多个备选方案（不同预算/风格）。"""
    session = await db.get(Session, req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    result = await db.execute(
        select(Itinerary).where(Itinerary.session_id == req.session_id)
    )
    itinerary_obj = result.scalar_one_or_none()
    if not itinerary_obj:
        raise HTTPException(status_code=404, detail="未生成行程")

    base_itinerary = itinerary_obj.plan
    requirements = base_itinerary.get("requirements", {})

    # 为每种风格生成方案提示词
    alternatives = []
    base_budget = float(requirements.get("budget", 3000))

    style_configs = {
        "预算型": {"budget_factor": 0.7, "description": "经济实惠，注重性价比"},
        "舒适型": {"budget_factor": 1.0, "description": "平衡品质与价格"},
        "豪华型": {"budget_factor": 1.5, "description": "高端品质，享受体验"}
    }

    for style in req.styles:
        if style not in style_configs:
            continue

        config = style_configs[style]
        new_budget = int(base_budget * config["budget_factor"])

        # 构造简化的行程方案
        alternative = {
            "style": style,
            "description": config["description"],
            "budget": new_budget,
            "requirements": {
                **requirements,
                "budget": new_budget,
                "preferences": f"{requirements.get('preferences', '')} ({style})"
            },
            "summary": f"{style}方案 - 预算 ¥{new_budget}"
        }

        alternatives.append(alternative)

    return {
        "base_itinerary": base_itinerary,
        "alternatives": alternatives,
        "message": f"已生成 {len(alternatives)} 个备选方案"
    }


@router.post("/select-alternative")
async def select_alternative(
    session_id: int,
    style: str,
    db: AsyncSession = Depends(get_db)
):
    """选择一个备选方案并重新生成完整行程。"""
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    result = await db.execute(
        select(Itinerary).where(Itinerary.session_id == session_id)
    )
    itinerary_obj = result.scalar_one_or_none()
    if not itinerary_obj:
        raise HTTPException(status_code=404, detail="未生成行程")

    base_itinerary = itinerary_obj.plan
    requirements = base_itinerary.get("requirements", {})

    # 根据选择的风格调整预算
    base_budget = float(requirements.get("budget", 3000))
    style_configs = {
        "预算型": 0.7,
        "舒适型": 1.0,
        "豪华型": 1.5
    }

    new_budget = int(base_budget * style_configs.get(style, 1.0))

    # 构造重新生成的提示
    prompt = f"请根据{style}方案重新规划行程，预算调整为 ¥{new_budget}。"

    return {
        "message": f"已选择{style}方案，正在重新生成行程...",
        "new_budget": new_budget,
        "prompt": prompt
    }
