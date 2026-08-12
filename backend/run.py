"""后端启动入口。

Windows 上 psycopg 3 的 async 模式必须用 Selector 事件循环，而 uvicorn
在 import app 之前就创建事件循环（Proactor），因此必须在 uvicorn.run 之前
设置 WindowsSelectorEventLoopPolicy。

用法: .venv/Scripts/python run.py
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
