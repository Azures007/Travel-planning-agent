"""FastAPI 主应用。"""

import asyncio
import logging
import sys

# Windows: psycopg 3 async 需要 selector 事件循环（必须在事件循环创建前设置）
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 让 app 的 INFO 日志可见（如上下文压缩、校验重试等）
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, sessions
from app.config import settings
from app.db.base import Base
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # P1：启动时自动建表（后续迁移可换 Alembic）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Travel Planning Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(chat.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
