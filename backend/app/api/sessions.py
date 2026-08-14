from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Itinerary, Message, Session
from app.db.session import get_db
from app.schemas import ItineraryPlan

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class RenameRequest(BaseModel):
    title: str


@router.patch("/{session_id}")
async def rename_session(session_id: int, req: RenameRequest, db: AsyncSession = Depends(get_db)):
    """重命名会话标题。"""
    session = await db.get(Session, session_id)
    if session is None:
        return {"error": "会话不存在"}
    title = req.title.strip()
    if not title:
        return {"error": "标题不能为空"}
    session.title = title[:200]
    await db.commit()
    return {"id": session.id, "title": session.title}


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


@router.delete("/{session_id}")
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db)):
    """删除会话：清掉消息/行程 + LangGraph checkpoint 状态。"""
    session = await db.get(Session, session_id)
    if session is None:
        return {"error": "会话不存在"}

    # 删除应用数据（messages/itineraries 由外键级联删除）
    await db.execute(delete(Message).where(Message.session_id == session_id))
    await db.execute(delete(Itinerary).where(Itinerary.session_id == session_id))
    await db.delete(session)
    await db.commit()

    # 删除 LangGraph checkpoint 状态（thread_id 前缀 session-{id}）
    from sqlalchemy import text

    thread_prefix = f"session-{session_id}"
    for table in ("checkpoint_blobs", "checkpoint_writes", "checkpoints"):
        await db.execute(
            text(f"DELETE FROM {table} WHERE thread_id = :tid")
            .bindparams(tid=thread_prefix)
        )
    await db.commit()

    return {"deleted": session_id}


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

    # 读取 checkpointer 中是否有待回答的问题（前端恢复等待状态）
    from app.agent.runner import AgentRunner

    pending_question = await AgentRunner.get_pending_question(session_id)

    return {
        "id": session.id,
        "title": session.title,
        "pending_question": pending_question,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
            }
            for m in messages
            # tool 角色是给模型看的工具结果，不应作为对话历史展示给用户
            if m.role != "tool"
        ],
        "itinerary": latest_itinerary.plan if latest_itinerary else None,
    }
