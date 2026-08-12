"""AgentRunner：LangGraph 图编排层。

职责：
- 构建并缓存 graph（含 checkpointer）
- 判断新消息 vs 中断恢复，构造 astream 输入
- 消费 custom/updates 流，转换为 SSE AgentEvent
- 中断/结束时把 state.messages 增量同步回 DB（含 tool_calls）
- 读 pending_question 供前端恢复等待状态
"""

import logging
from typing import AsyncIterator

from langgraph.types import Command
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.events import AgentEvent
from app.agent.graph import build_graph
from app.agent.llm import LLM
from app.agent.nodes import set_llm
from app.config import settings
from app.db.models import Message, Session

logger = logging.getLogger(__name__)

# 图实例缓存（keyed by llm 参数，实际单例）
_graph_cache = None


async def get_graph():
    """获取编译后的 LangGraph 图（全局单例）。"""
    global _graph_cache
    if _graph_cache is None:
        from app.agent.checkpointer import get_checkpointer

        checkpointer = await get_checkpointer()
        _graph_cache = build_graph(checkpointer)
    return _graph_cache


class AgentRunner:
    def __init__(self, llm: LLM):
        set_llm(llm)
        self.llm = llm

    @staticmethod
    async def _get_graph():
        return await get_graph()

    @staticmethod
    def _thread_id(session_id: int) -> dict:
        return {"configurable": {"thread_id": f"session-{session_id}"}, "recursion_limit": 30}

    async def run(self, db: AsyncSession, session_id: int, content: str) -> AsyncIterator[AgentEvent]:
        """执行 agent 循环，产出 SSE 事件流。"""
        graph = await self._get_graph()
        config = self._thread_id(session_id)

        # 判断是否处于中断恢复状态
        snap = await graph.aget_state(config)
        is_resume = bool(snap and snap.interrupts)

        if is_resume:
            # 恢复路径：不预落库用户消息（ask_user 追加进 state，同步时写库）
            payload: object = Command(resume=content)
        else:
            # 新消息：先落库（防中途失败丢失），再全量加载历史 seed 图
            db.add(Message(session_id=session_id, role="user", content=content))
            await db.commit()
            history = await self._load_history(db, session_id)
            payload = {"messages": history}

        try:
            async for _mode, chunk in graph.astream(payload, config, stream_mode=["custom", "updates"]):
                if _mode == "custom":
                    yield self._map_custom(chunk)
        except Exception as e:
            # 递归超限或执行错误
            logger.error("Agent 执行出错: %s", e)
            yield AgentEvent("error", {"message": f"Agent 执行出错: {e}"})
            yield AgentEvent("done", {})
            return

        # 中断还是正常结束
        snap = await graph.aget_state(config)
        if snap and snap.interrupts:
            await self._sync_messages(db, session_id, snap.values.get("messages") or [])
            interrupt_value = snap.interrupts[0].value or {}
            yield AgentEvent(
                "question",
                {"question": interrupt_value.get("question", ""), "waiting": True},
            )
            return  # 不发 done，流自然关闭

        await self._sync_messages(db, session_id, snap.values.get("messages") or [])

        # 输出行程
        itinerary = snap.values.get("itinerary")
        if itinerary:
            yield AgentEvent("itinerary", {"plan": itinerary})
            validation = snap.values.get("validation") or {}
            warnings = [i for i in validation.get("issues", []) if i["level"] == "warning"]
            if warnings:
                yield AgentEvent("validation_report", {"warnings": warnings})

        # 更新会话标题
        session = await db.get(Session, session_id)
        if session and itinerary:
            session.title = itinerary.get("title") or session.title
            await db.commit()

        yield AgentEvent("done", {})

    @staticmethod
    def _map_custom(chunk) -> AgentEvent:
        """把 custom 流事件映射为 AgentEvent。"""
        kind = chunk.get("type", "")
        return AgentEvent(kind, chunk.get("data", {}))

    @staticmethod
    async def _load_history(db: AsyncSession, session_id: int) -> list[dict]:
        """加载会话历史为 OpenAI 兼容消息格式。"""
        result = await db.execute(
            select(Message).where(Message.session_id == session_id).order_by(Message.id)
        )
        messages = result.scalars().all()
        history: list[dict] = []
        for m in messages:
            msg: dict = {"role": m.role, "content": m.content}
            if m.tool_calls:
                msg["tool_calls"] = m.tool_calls
            history.append(msg)
        return history

    @staticmethod
    async def _sync_messages(db: AsyncSession, session_id: int, graph_messages: list[dict]) -> None:
        """把图内 messages 增量同步回 DB（含 tool_calls 列）。"""
        count_result = await db.execute(
            select(func.count()).select_from(Message).where(Message.session_id == session_id)
        )
        existing = count_result.scalar() or 0

        if len(graph_messages) < existing:
            # 异常：重放/漂移 → 整体重建
            logger.warning("会话 %s 消息漂移（db=%s, graph=%s），重建", session_id, existing, len(graph_messages))
            from sqlalchemy import delete

            await db.execute(delete(Message).where(Message.session_id == session_id))
            existing = 0

        for m in graph_messages[existing:]:
            db.add(
                Message(
                    session_id=session_id,
                    role=m.get("role", "assistant"),
                    content=m.get("content", ""),
                    tool_calls=m.get("tool_calls"),
                )
            )
        await db.commit()

    @staticmethod
    async def get_pending_question(session_id: int) -> str | None:
        """读取会话当前是否有待回答的问题（供 GET /sessions/{id} 恢复等待态）。"""
        graph = await get_graph()
        config = {"configurable": {"thread_id": f"session-{session_id}"}}
        snap = await graph.aget_state(config)
        if snap and snap.interrupts:
            value = snap.interrupts[0].value or {}
            return value.get("question")
        return None
