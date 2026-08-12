"""Step 0 冒烟测试：验证 AsyncPostgresSaver + interrupt 在真实 Postgres 上往返。

验证点：
1. AsyncPostgresSaver 建表 + 持久化
2. interrupt 触发暂停，aget_state 读到 interrupts
3. Command(resume=...) 恢复续跑，interrupt 返回值正确
4. 状态中的 messages 跨请求保留

用法: .venv/Scripts/python -m app.smoke_test_interrupt
"""

import asyncio
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt

from app.agent.checkpointer import get_checkpointer


class SmokeState(TypedDict, total=False):
    messages: list[dict]
    value: int


def node_a(state):
    """进入后直接 interrupt，等待用户输入"""
    answer = interrupt({"type": "question", "question": "你准备好了吗？"})
    msgs = state.get("messages", [])
    msgs = msgs + [{"role": "user", "content": answer}]
    return {"messages": msgs, "value": 1}


def node_b(state):
    msgs = state.get("messages", []) + [{"role": "assistant", "content": "收到，继续！"}]
    return {"messages": msgs, "value": state.get("value", 0) + 10}


def build_graph(checkpointer):
    g = StateGraph(SmokeState)
    g.add_node("a", node_a)
    g.add_node("b", node_b)
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("b", END)
    return g.compile(checkpointer=checkpointer)


async def main():
    checkpointer = await get_checkpointer()
    graph = build_graph(checkpointer)

    config = {"configurable": {"thread_id": "smoke-test-1"}}

    # 1. 首次执行：触发 interrupt
    print("== 首次执行（触发 interrupt）==")
    try:
        async for chunk in graph.astream({"messages": []}, config):
            print("chunk:", chunk)
    except Exception as e:
        print(f"astream 中断异常（预期）: {type(e).__name__}")

    # 2. 读状态，确认 interrupts
    snap = await graph.aget_state(config)
    print(f"interrupts 数量: {len(snap.interrupts)}")
    if snap.interrupts:
        print(f"interrupt value: {snap.interrupts[0].value}")
    print(f"value: {snap.values.get('value')}")
    print(f"messages: {snap.values.get('messages')}")

    # 3. 恢复：Command(resume=...)
    print("== 恢复执行 ==")
    async for chunk in graph.astream(Command(resume="准备好了！"), config):
        print("chunk:", chunk)

    # 4. 最终状态
    snap2 = await graph.aget_state(config)
    print(f"最终 value: {snap2.values.get('value')}")
    print(f"最终 messages: {snap2.values.get('messages')}")
    print(f"最终 interrupts: {len(snap2.interrupts)}")

    assert snap2.values.get("value") == 11, "value 应为 11"
    assert len(snap2.values.get("messages", [])) == 2, "messages 应为 2 条"
    assert len(snap2.interrupts) == 0, "恢复后不应再有 interrupt"
    print("\n[OK] 冒烟测试通过：AsyncPostgresSaver + interrupt + 恢复 全部正常")


if __name__ == "__main__":
    asyncio.run(main())
