import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import LLM
from app.agent.runner import AgentRunner
from app.config import settings
from app.db.models import Session
from app.db.session import get_db

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: int
    content: str


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _make_llm() -> LLM:
    return LLM(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        model=settings.dashscope_model,
    )


@router.post("/chat")
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, req.session_id)
    if session is None:
        return {"error": "会话不存在"}

    runner = AgentRunner(_make_llm())

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for ev in runner.run(db, req.session_id, req.content):
                yield _sse({"type": ev.kind, "data": ev.data})
        except Exception as e:
            yield _sse({"type": "error", "data": {"message": AgentRunner._friendly_error(e)}})
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
