from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Itinerary, Message, Session
from app.db.session import get_db
from app.schemas import ItineraryPlan

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("")
async def create_session(db: AsyncSession = Depends(get_db)):
    session = Session(title="新行程规划")
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return {"id": session.id, "title": session.title}


@router.get("")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session).order_by(Session.created_at.desc()).limit(50)
    )
    sessions = result.scalars().all()
    return [
        {"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()}
        for s in sessions
    ]


@router.get("/{session_id}")
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if session is None:
        return {"error": "会话不存在"}

    msg_result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.id)
    )
    messages = msg_result.scalars().all()

    itin_result = await db.execute(
        select(Itinerary)
        .where(Itinerary.session_id == session_id)
        .order_by(Itinerary.id.desc())
        .limit(1)
    )
    latest_itinerary = itin_result.scalars().first()

    return {
        "id": session.id,
        "title": session.title,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
            }
            for m in messages
        ],
        "itinerary": latest_itinerary.plan if latest_itinerary else None,
    }
