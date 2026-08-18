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

from app.api import chat, sessions, export, edit, compare, geocode_simple as geocode
from app.config import settings
from app.db.base import Base
from app.db.session import engine
from app.middleware import RequestLoggingMiddleware, RateLimitMiddleware


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

# 请求日志与性能监控（记录耗时、慢请求告警、请求 ID）
app.add_middleware(RequestLoggingMiddleware)

# 限流：每 IP 每分钟最多 300 次 API 请求（防滥用，正常使用不受影响）
app.add_middleware(RateLimitMiddleware, max_requests=300, window_seconds=60)

app.include_router(sessions.router)
app.include_router(chat.router)
app.include_router(export.router)
app.include_router(edit.router)
app.include_router(compare.router)
app.include_router(geocode.router)


# 全局异常处理器：统一返回结构化错误信息
from fastapi import Request
from fastapi.responses import JSONResponse


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """捕获未处理的异常，返回结构化 JSON 错误，避免泄露堆栈细节。"""
    logging.exception(f"未处理的异常: {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器处理请求时出错，请稍后重试",
            "path": str(request.url.path),
        },
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}
