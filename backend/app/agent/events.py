"""Agent SSE 事件类型定义。"""


class AgentEvent:
    """SSE 事件类型"""

    def __init__(self, kind: str, data: dict):
        self.kind = kind
        self.data = data
