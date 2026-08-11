import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import AgentRunner
from app.config import settings
from app.db.models import Itinerary, Message, Session
from app.db.session import get_db
from app.schemas import ItineraryPlan

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: int
    content: str


async def _load_history(db: AsyncSession, session_id: int) -> list[dict]:
    """加载会话历史为 OpenAI 兼容消息格式。"""
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.id)
    )
    messages = result.scalars().all()
    history: list[dict] = []
    for m in messages:
        msg: dict = {"role": m.role, "content": m.content}
        if m.tool_calls:
            msg["tool_calls"] = m.tool_calls
        history.append(msg)
    return history


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, req.session_id)
    if session is None:
        return {"error": "会话不存在"}

    # 持久化用户消息
    db.add(Message(session_id=req.session_id, role="user", content=req.content))
    await db.commit()

    # 加载历史（含刚保存的用户消息），构造 agent 输入
    history = await _load_history(db, req.session_id)

    runner = AgentRunner(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        model=settings.dashscope_model,
    )

    async def event_stream() -> AsyncIterator[str]:
        assistant_parts: list[str] = []
        itinerary_plan: ItineraryPlan | None = None

        try:
            async for event in runner.run(history):
                if event.kind == "agent_message":
                    assistant_parts.append(event.data["text"])
                elif event.kind == "itinerary":
                    itinerary_plan = ItineraryPlan.model_validate(event.data["plan"])
                # tool_result 事件不直接透传给前端（当前 UI 不需要展示）
                yield _sse({"type": event.kind, "data": event.data})
        except Exception as e:
            yield _sse({"type": "error", "data": {"message": f"Agent 执行出错: {e}"}})
        finally:
            # 持久化 assistant 消息
            if assistant_parts:
                db.add(
                    Message(
                        session_id=req.session_id,
                        role="assistant",
                        content="".join(assistant_parts),
                    )
                )
            # 持久化行程
            if itinerary_plan is not None:
                db.add(
                    Itinerary(
                        session_id=req.session_id,
                        plan=itinerary_plan.model_dump(),
                    )
                )
                # 更新会话标题
                session.title = itinerary_plan.title
            await db.commit()
            yield _sse({"type": "done", "data": {}})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
